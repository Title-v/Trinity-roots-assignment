# Deploying to Vercel

[Back to README](../README.md)

Production: [trinity-roots-title-v.vercel.app](https://trinity-roots-title-v.vercel.app).

This project uses **Vercel Services (beta)** to deploy the Vite frontend and FastAPI backend together. `vercel.json` routes `/api/*` to FastAPI and other requests to the frontend. The SPA rewrite supports direct links to `/booking` and `/my-bookings`.

## Runtime settings

Set these environment variables on the Vercel project. Keep credentials as Secrets, without a `VITE_` prefix.

| Variable | Value or purpose |
| --- | --- |
| `DATABASE_URL` | Pooled connection URL for the intended Neon database, retaining SSL parameters |
| `OPENAI_API_KEY` | Existing model-provider key, needed for the assistant |
| `OPENAI_MODEL` | Model name, currently `gpt-6-luna` |
| `SESSION_SECRET` | A stable random secret shared across function instances and redeployments |
| `API_ROOT_PATH` | `/api`, so FastAPI docs and request routing use the public API prefix |
| `ASSISTANT_AUDIT_BACKEND` | `database`, to persist exact model request/response logs |
| `UV_NO_DEV` | `1`, to omit Python development dependencies during deployment |
| `CYPRESS_INSTALL_BINARY` | `0`, because the UI test browser is not needed for deployment |

Use Node.js 24. The backend's `.python-version` selects Python 3.12. Runtime services are configured in Singapore (`sin1`) near the existing Neon database. Deployments do not automatically run migrations or seed scripts.

## Database migration

Apply migrations using the intended database's direct connection before releasing code that needs them:

```sh
cd backend
uv run alembic upgrade head
cd ..
```

The deployment migration adds `assistant_audit_logs`; it does not replace or clear users, resources, or bookings. Production credentials should not be copied into Preview environments. A preview requiring database access should use a separate test database.

## Audit logs

Local development continues to write `.assistant-audit.jsonl` with owner-only permissions. With `ASSISTANT_AUDIT_BACKEND=database`, events are saved in `assistant_audit_logs` instead, because a function's local filesystem is not durable storage.

Each row stores the request ID, event type, exact body text, HTTP response status when available, and UTC timestamp. There is no public API for reading these records. Use an authorized database connection or the Neon SQL editor, for example:

```sql
SELECT request_id, event, status, created_at, body
FROM assistant_audit_logs
ORDER BY id DESC
LIMIT 10;
```

Masking happens before a model request is sent. Response bodies remain verbatim, so logs can still contain personal data missed by the recognizers or returned by the model. Automated retention and deletion are not implemented. Database access must remain restricted.

## Deploy and verify

Log in to the Vercel CLI, link the intended project and team, and configure its production variables. Use stdin or the dashboard when setting secret values, rather than putting them in command-line arguments.

```sh
npx vercel login
npx vercel link
npm run build
npx vercel deploy --prod --skip-domain
```

Check the staged deployment before assigning the production domain:

- The homepage and direct `/booking` and `/my-bookings` links load.
- `/api/health` and `/api/health/db` return healthy responses.
- Registration, login, booking, editing and cancellation work through the same origin.
- A model request produces an assistant reply and a paired durable audit record.

Then promote the verified production deployment:

```sh
npx vercel promote <deployment-url>
```

The production form does not depend on the model provider. In-memory rate limits still apply per function instance, not across all Vercel instances. Availability polling and database overlap constraints retain their existing behavior.
