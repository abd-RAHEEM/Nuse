"""Create the Phase 2 Nuse schema.

Revision ID: 20261101_0001
Revises:
"""
from alembic import op

revision = "20261101_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS citext")
    connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    statements = """
        CREATE TABLE users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            username citext NOT NULL UNIQUE,
            pin_hash text NOT NULL,
            display_name text,
            timezone text NOT NULL DEFAULT 'Asia/Kolkata',
            settings jsonb NOT NULL DEFAULT '{}'::jsonb,
            last_login_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE sessions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash text NOT NULL UNIQUE,
            created_at timestamptz NOT NULL DEFAULT now(),
            last_seen_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            user_agent text,
            ip_hash text
        );
        CREATE INDEX sessions_user_id_idx ON sessions(user_id);
        CREATE TABLE login_attempts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            username_lower text NOT NULL,
            ip text NOT NULL,
            succeeded boolean NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX login_attempts_username_created_idx
            ON login_attempts(username_lower, created_at);
        CREATE INDEX login_attempts_ip_created_idx ON login_attempts(ip, created_at);
        CREATE TABLE jobs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_url text,
            normalized_url text,
            company text NOT NULL,
            title text NOT NULL,
            location text,
            employment_type text,
            work_mode text,
            external_job_id text,
            description text,
            requirements text,
            deadline date,
            notes text,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            field_provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
            extraction_id uuid,
            archived_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT jobs_normalized_url_length CHECK (normalized_url IS NULL OR length(normalized_url) <= 2048)
        );
        CREATE UNIQUE INDEX jobs_user_normalized_url_idx
            ON jobs(user_id, normalized_url) WHERE normalized_url IS NOT NULL;
        CREATE INDEX jobs_user_created_idx ON jobs(user_id, created_at DESC);
        CREATE TABLE applications (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            job_id uuid NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
            status text NOT NULL CHECK (status IN ('applied', 'assessment', 'interview', 'offer', 'rejected', 'withdrawn', 'on_hold')),
            applied_on date,
            next_follow_up_on date,
            notes text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX applications_user_status_idx ON applications(user_id, status);
        CREATE TABLE job_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            application_id uuid REFERENCES applications(id) ON DELETE SET NULL,
            type text NOT NULL,
            title text NOT NULL,
            notes text,
            occurred_at timestamptz NOT NULL DEFAULT now(),
            scheduled_for timestamptz,
            all_day boolean NOT NULL DEFAULT false,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX job_events_job_occurred_idx ON job_events(job_id, occurred_at);
        CREATE INDEX job_events_user_scheduled_idx ON job_events(user_id, scheduled_for)
            WHERE scheduled_for IS NOT NULL;
        CREATE TABLE resources (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title text NOT NULL,
            category text NOT NULL,
            source_url text,
            normalized_url text,
            source_platform text,
            description text,
            summary text,
            notes text,
            is_favorite boolean NOT NULL DEFAULT false,
            is_saved_for_later boolean NOT NULL DEFAULT false,
            verification_status text NOT NULL DEFAULT 'unverified',
            verification_note text,
            field_provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
            extraction_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX resources_user_normalized_url_idx
            ON resources(user_id, normalized_url) WHERE normalized_url IS NOT NULL;
        CREATE INDEX resources_user_category_idx ON resources(user_id, category);
        CREATE TABLE resource_details (
            resource_id uuid PRIMARY KEY REFERENCES resources(id) ON DELETE CASCADE,
            data jsonb NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE TABLE tags (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name text NOT NULL,
            slug text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(user_id, slug)
        );
        CREATE TABLE job_tags (
            job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            tag_id uuid NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY(job_id, tag_id)
        );
        CREATE TABLE resource_tags (
            resource_id uuid NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
            tag_id uuid NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY(resource_id, tag_id)
        );
        CREATE TABLE collections (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name text NOT NULL,
            description text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE collection_resources (
            collection_id uuid NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
            resource_id uuid NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
            added_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY(collection_id, resource_id)
        );
        CREATE TABLE extractions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type text NOT NULL CHECK (type IN ('job', 'resource')),
            input_url text,
            normalized_url text,
            input_text text,
            detected_source_kind text,
            detected_domain text,
            detected_type text,
            status text NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'consumed')),
            result jsonb,
            error_code text,
            error_message text,
            provider_trace jsonb NOT NULL DEFAULT '{}'::jsonb,
            attempts integer NOT NULL DEFAULT 0,
            started_at timestamptz,
            finished_at timestamptz,
            expires_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX extractions_user_status_idx ON extractions(user_id, status);
        ALTER TABLE jobs ADD CONSTRAINT jobs_extraction_fk
            FOREIGN KEY (extraction_id) REFERENCES extractions(id) ON DELETE SET NULL;
        ALTER TABLE resources ADD CONSTRAINT resources_extraction_fk
            FOREIGN KEY (extraction_id) REFERENCES extractions(id) ON DELETE SET NULL;
        CREATE TABLE integration_connections (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider text NOT NULL CHECK (provider IN ('notion', 'google_calendar')),
            status text NOT NULL,
            encrypted_credentials bytea,
            scopes jsonb NOT NULL DEFAULT '[]'::jsonb,
            account_label text,
            config jsonb NOT NULL DEFAULT '{}'::jsonb,
            last_used_at timestamptz,
            last_error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(user_id, provider)
        );
        CREATE TABLE external_links (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            entity_type text NOT NULL CHECK (entity_type IN ('resource', 'job_event')),
            entity_id uuid NOT NULL,
            provider text NOT NULL,
            external_id text NOT NULL,
            external_url text,
            last_synced_at timestamptz,
            UNIQUE(user_id, entity_type, entity_id, provider)
        );
        CREATE TABLE idempotency_keys (
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key text NOT NULL,
            method text NOT NULL,
            path text NOT NULL,
            request_hash text NOT NULL,
            response_status integer,
            response_body jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            PRIMARY KEY(user_id, key)
        );
        """.split(";\n")
    for statement in statements:
        if statement.strip():
            connection.exec_driver_sql(statement)


def downgrade() -> None:
    connection = op.get_bind()
    statements = """
        DROP TABLE IF EXISTS collection_resources, collections, resource_tags,
        job_tags, tags, resource_details, resources, job_events, applications,
        jobs, idempotency_keys, external_links, integration_connections,
        extractions, login_attempts, sessions, users CASCADE;
        """.split(";\n")
    for statement in statements:
        if statement.strip():
            connection.exec_driver_sql(statement)
