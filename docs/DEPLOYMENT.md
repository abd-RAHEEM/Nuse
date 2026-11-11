# Nuse setup and deployment

Nuse can run locally in mock mode, or as a full stack with a PostgreSQL
database. The web app proxies API requests through its own origin; the browser
does not call the API host directly.

## Requirements

- Node.js 20.9 or newer and pnpm
- Python 3.12 or newer and `uv`
- PostgreSQL for live mode

## Frontend preview

The mock frontend needs no API or database:

```powershell
Set-Location apps\web
Copy-Item .env.example .env.local
pnpm install --frozen-lockfile
pnpm dev
```

Open `http://localhost:3000`.

## Run the full stack locally

1. Copy `apps\api\.env.example` to `apps\api\.env`.
2. Set `DATABASE_URL`, `SESSION_SECRET`, `PIN_PEPPER`, and
   `INTEGRATION_ENCRYPTION_KEY`. Use a PostgreSQL database you control.
3. Install dependencies and apply migrations:

   ```powershell
   Set-Location apps\api
   uv sync
   uv run alembic upgrade head
   ```

4. Start the API:

   ```powershell
   uv run uvicorn hub.main:app --reload --host 127.0.0.1 --port 8000
   ```

5. In another terminal, copy `apps\web\.env.example` to
   `apps\web\.env.local` and set:

   ```dotenv
   NEXT_PUBLIC_API_MODE=live
   API_PROXY_TARGET=http://127.0.0.1:8000
   ```

6. Start the web app:

   ```powershell
   Set-Location apps\web
   pnpm install --frozen-lockfile
   pnpm dev
   ```

Check API readiness at `http://127.0.0.1:8000/health/ready`.

### Secrets and optional integrations

Keep `.env` files out of Git. Generate unique values for each environment:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Use the first two values for `SESSION_SECRET` and `PIN_PEPPER`, and the third
for `INTEGRATION_ENCRYPTION_KEY`. Optional Notion, Google Calendar, and Gmail
credentials belong only in the API environment. Use the callback URLs for your
own API host when configuring OAuth providers. Gmail read access may require
additional Google verification for public use.

`ALLOW_SIGNUP=true` keeps registration open. Set it to `false` only to pause new
registrations.

## Deploy the API to Render

1. Create a PostgreSQL database with a provider of your choice and copy its
   connection string.
2. In Render, create a Blueprint from this repository and review `render.yaml`.
   The API service uses `apps/api` as its root directory.
3. Set the Blueprint's unsynchronized environment values, especially
   `DATABASE_URL`, Google OAuth values (if using those integrations), and
   `WEB_ORIGIN`. Keep secrets in Render's environment settings.
4. Apply migrations to the selected database:

   ```powershell
   Set-Location apps\api
   uv sync
   uv run alembic upgrade head
   ```

5. Confirm the service health check succeeds at `/health/ready`.

The Blueprint uses `uv sync --no-dev` to build and Uvicorn to start the API.
Set `ALLOW_SIGNUP=true` to keep account creation open.

## Deploy the web app to Vercel

1. Import the repository into Vercel.
2. Set the project root directory to `apps/web`.
3. Set these environment variables for the deployment:

   ```dotenv
   NEXT_PUBLIC_API_MODE=live
   API_PROXY_TARGET=https://<your-api-service>.onrender.com
   ```

   `API_PROXY_TARGET` is the API origin only; do not append `/api/v1`.
4. In Render, set `WEB_ORIGIN` to your Vercel deployment origin.
5. If using OAuth integrations, register callback URLs based on your own API
   service origin with each provider.

For Preview deployments, use mock mode or a separate API and database. Do not
point previews at production data unless that is intentional.

## Verification

From `apps/api`:

```powershell
uv run ruff check src tests
uv run pytest
```

From `apps/web`:

```powershell
pnpm lint
npx tsc --noEmit
pnpm build
```

Database-backed integration tests require `DATABASE_URL`. Before relying on a
production instance, verify login, one authenticated read/write flow, HTTPS
session cookies, backups, and a database restore.

Never commit credentials, `.env` files, local editor configuration, or private
project-planning notes.
