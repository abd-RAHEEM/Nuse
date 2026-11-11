# Nuse API contracts

Phase 2 contract baseline for the FastAPI service. The API uses `/api/v1`,
camelCase JSON, UUID identifiers, ISO 8601 UTC timestamps, and RFC 9457
`application/problem+json` errors.

## Authentication

The API uses an opaque `hub_session` HttpOnly cookie. Mutating requests also
send `X-Requested-With: hub`; requests without that header are rejected before
they reach a router.

| Method | Path | Success |
| --- | --- | --- |
| POST | `/auth/signup` | `201 { user }` and session cookie |
| POST | `/auth/login` | `200 { user }` and session cookie |
| POST | `/auth/logout` | `204` |
| GET | `/auth/me` | `200 { user }` |
| POST | `/auth/change-pin` | `204` |
| POST | `/auth/logout-all` | `204` |

Signup and login accept `{ username, pin }`. The username is lowercase,
case-insensitive, and 3–32 characters. The PIN is exactly six digits.
Five failed attempts from the same username and IP within 15 minutes produce a
temporary `423 account_locked` response. Unknown usernames and incorrect PINs
share the same `401 invalid_credentials` response.

## Shared response shapes

```ts
type Page<T> = { items: T[]; nextCursor: string | null };
type TagRef = { id: string; name: string };
type Problem = {
  type: string;
  title: string;
  status: number;
  code: string;
  detail?: string;
  requestId: string;
  errors?: { field: string; message: string; code: string }[];
};
```

## Jobs

| Method | Path | Success |
| --- | --- | --- |
| GET | `/jobs` | `200 Page<JobSummary>` |
| POST | `/jobs` | `201 JobDetail` |
| GET | `/jobs/{id}` | `200 JobDetail` |
| PATCH | `/jobs/{id}` | `200 JobDetail` |
| DELETE | `/jobs/{id}` | `204` |
| GET | `/jobs/check-duplicate?url=` | `200 duplicate result` |
| POST | `/jobs/{id}/events` | `201 JobEvent` |
| PATCH | `/jobs/{id}/events/{eventId}` | `200 JobEvent` |
| DELETE | `/jobs/{id}/events/{eventId}` | `204` |

Job list filters are query parameters: `q`, `status[]`, `company`, `location`,
`tag[]`, `appliedFrom`, `appliedTo`, `followUpBefore`, `archived`, `sort`,
`cursor`, and `limit`.

Creating an applied job creates its application and system events in one
transaction. A saved job has no application row.

The initial backend slice implements the user-scoped list, detail, create,
update, delete, and event-create operations. The remaining filters, duplicate
check, event edit/delete, idempotency replay, and full RFC 9457 error mapping
are tracked for the next backend slice.

## Resources, tags, and collections

| Method | Path | Success |
| --- | --- | --- |
| GET/POST | `/resources` | `200 Page<ResourceSummary>` / `201 ResourceDetail` |
| GET/PATCH/DELETE | `/resources/{id}` | `200 ResourceDetail` / `200 ResourceDetail` / `204` |
| GET | `/tags` | `200 { items }` |
| PATCH/DELETE | `/tags/{id}` | `200 tag` / `204` |
| GET/POST | `/collections` | `200 { items }` / `201 collection` |
| PATCH/DELETE | `/collections/{id}` | `200 collection` / `204` |
| PUT/DELETE | `/collections/{id}/resources/{resourceId}` | `204` / `204` |

These routes are implemented with authenticated `user_id` scoping. Resource
responses include tag references and collection IDs; collection responses
include resource counts, and tag responses include job/resource counts.

## Dashboard and settings

| Method | Path | Success |
| --- | --- | --- |
| GET | `/dashboard` | `200 DashboardResponse` |
| GET/PATCH | `/settings` | `200 settings` / `200 settings` |

Dashboard responses contain user details, application counts, upcoming items,
recent activity, and recent resources. All date computations use the user's
IANA timezone.

The committed OpenAPI document is checked in CI-style tests against the runtime
FastAPI schema, including camelCase properties such as `displayName`,
`applicationsTracked`, `recentActivity`, and `resourceCount`.

## Smart Capture

| Method | Path | Success |
| --- | --- | --- |
| POST | `/extractions` | `202 Extraction` |
| GET | `/extractions/{id}` | `200 Extraction` |
| DELETE | `/extractions/{id}` | `204` |

At least one of `url` or `text` is required. The client polls the extraction
resource until it reaches `succeeded`, `partial`, or `failed`. Saving a draft
is a separate explicit job or resource mutation.

## Invariants

- Every personal query is scoped by authenticated `user_id`.
- A second application for the same job is rejected.
- Normalized URLs are unique per user where present.
- Cross-user records return `404`, not `403`.
- Creating records supports an `Idempotency-Key` header.
- Mutating requests without the CSRF header are rejected.

## Gmail application updates

Gmail is opt-in and requests only
`https://www.googleapis.com/auth/gmail.readonly`. The initial sync searches the
most recent 90 days for likely job-application messages; later syncs use the
Gmail history cursor. Nuse never sends, moves, or deletes mail and does not call
Gmail's attachment endpoint. Gmail's full-message response can include small
attachment parts inline; the parser skips those parts and does not store them.
Message bodies are processed in memory by local rules and are never stored or
sent to an external AI service. A message without a strict company-and-role
match is discarded and is not added to the database.

| Method | Path | Success |
| --- | --- | --- |
| POST | `/integrations/gmail/oauth/start` | `200 { authUrl }` |
| GET | `/integrations/gmail/oauth/callback` | `302` to Settings |
| DELETE | `/integrations/gmail` | `204` |
| POST | `/integrations/gmail/sync` | `202 GmailSyncRun` |
| POST | `/integrations/gmail/sync/{runId}/step` | `200 GmailSyncRun` |
| GET | `/integrations/gmail/review` | `200 { items: GmailReviewItem[] }` |
| POST | `/integrations/gmail/review/{messageId}` | `200 { status, jobId }` |

Sync is a durable, resumable database-backed run advanced in bounded API
steps. Repeated start requests resume the active run. The client advances a
step at a time and shows the persisted counts. No Redis or worker service is
required; the run state allows a separate worker to be introduced if measured
mailbox volume warrants it.

```ts
type GmailSyncRun = {
  id: string;
  status: 'running' | 'completed' | 'failed';
  mode: 'initial' | 'incremental';
  messagesScanned: number;
  jobsMatched: number;
  jobsUpdated: number;
  reviewQueued: number;
  unmatchedDiscarded: number;
  lastError: string | null;
  createdAt: string;
  finishedAt: string | null;
};

type GmailReviewItem = {
  messageId: string;
  jobId: string;
  company: string;
  title: string;
  sender: string | null;
  subject: string;
  receivedAt: string;
  suggestedStatus: JobStatus | null;
};
```

Only a strict job match is retained. The stored message record contains its
Gmail message ID, matched job, sender, subject, received time, suggested stage,
and processing state; it contains no body or attachment data. Clear matches
that represent a valid stage advance update the application and write a job
timeline event in the same transaction. A matched message with an uncertain
stage goes to review; the owner can apply a stage or ignore it. Gmail history
IDs and pagination cursors are private server state and are never returned in
the integration config.

Disconnecting Gmail deletes the saved refresh token, sync runs, and matched
message metadata; it never changes or deletes Gmail messages.

Because `gmail.readonly` is a restricted Google OAuth scope, a public shared
OAuth app requires Google's restricted-scope verification and may require a
security assessment. Self-hosted deployments supply their own Google OAuth
client credentials and are responsible for Google's current consent-screen
and verification requirements.
