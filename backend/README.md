# Backend development

From this directory, run:

```bash
uv run python dev.py
```

The API runs at http://127.0.0.1:8000. Check `/health` for
`{"status":"ok"}`. The development server reloads Python source changes,
but excludes `.venv` so installed package changes do not restart the API.

## Database migrations

From the project root, run `neon checkout production` to select the project's
Neon branch and refresh the local database URLs. Restart the API after updating
the connection settings so it reads the new URL.

From this directory, run `uv run alembic upgrade head` to apply migrations
and `uv run alembic current` to show the applied revision. Alembic reads
`DATABASE_URL_UNPOOLED` from the environment or the project root's Neon env
file. The API uses the separate pooled `DATABASE_URL`.
