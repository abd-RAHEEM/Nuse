# Nuse entity relationship diagram

The database is PostgreSQL. Personal records carry `user_id`, and all foreign
keys declare their delete behavior in migrations.

```mermaid
erDiagram
    users ||--o{ sessions : owns
    users ||--o{ login_attempts : records
    users ||--o{ jobs : owns
    users ||--o{ applications : submits
    users ||--o{ job_events : records
    users ||--o{ resources : owns
    users ||--o{ tags : creates
    users ||--o{ collections : creates
    users ||--o{ extractions : starts
    users ||--o{ integration_connections : configures
    users ||--o{ external_links : maps
    users ||--o{ idempotency_keys : uses

    jobs ||--o| applications : receives
    jobs ||--o{ job_events : has
    jobs ||--o{ job_tags : labeled
    tags ||--o{ job_tags : labels

    resources ||--o| resource_details : describes
    resources ||--o{ resource_tags : labeled
    tags ||--o{ resource_tags : labels
    collections ||--o{ collection_resources : contains
    resources ||--o{ collection_resources : included

    extractions ||--o{ jobs : produces
    extractions ||--o{ resources : produces
    job_events ||--o{ external_links : linked
    resources ||--o{ external_links : linked

    users {
        uuid id PK
        citext username UK
        text pin_hash
        text display_name
        text timezone
    }
    jobs {
        uuid id PK
        uuid user_id FK
        text normalized_url
        text company
        text title
        text status "derived from application"
        timestamptz archived_at
    }
    applications {
        uuid id PK
        uuid user_id FK
        uuid job_id FK UK
        text status
        date applied_on
    }
    job_events {
        uuid id PK
        uuid user_id FK
        uuid job_id FK
        uuid application_id FK
        text type
        timestamptz occurred_at
        timestamptz scheduled_for
    }
    resources {
        uuid id PK
        uuid user_id FK
        text normalized_url
        text title
        text category
        boolean is_favorite
    }
    resource_details {
        uuid resource_id PK_FK
        jsonb data
    }
    tags {
        uuid id PK
        uuid user_id FK
        text name
        text slug
    }
    collections {
        uuid id PK
        uuid user_id FK
        text name
    }
    extractions {
        uuid id PK
        uuid user_id FK
        text type
        text status
        jsonb result
    }
```

The remaining support tables are `sessions`, `login_attempts`,
`job_tags`, `resource_tags`, `collection_resources`, `integration_connections`,
`external_links`, and `idempotency_keys`.
