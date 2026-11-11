# Trinity Roots Assignment

A resource booking app for rooms and equipment, built with React, FastAPI,
and Neon PostgreSQL. The current version includes a frontend connection check,
a database health endpoint, and the initial booking schema.

## Prerequisites

- Node.js 24 and npm
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Access to a Neon PostgreSQL database

From the project root, install the dependencies:

```sh
npm ci
npm --prefix frontend ci
uv sync --project backend --locked
```

Create `.env.local` in the project root. Copy the pooled and direct connection
strings from the Neon console and keep their SSL parameters.

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@POOLED_HOST/DB?sslmode=require
DATABASE_URL_UNPOOLED=postgresql://USER:PASSWORD@DIRECT_HOST/DB?sslmode=require
```

FastAPI uses the pooled URL through SQLAlchemy and Psycopg 3. Alembic uses the
direct URL. Git ignores the local environment file.

## Set up the database and start the app

In the first terminal, from the project root:

```sh
cd backend
uv run alembic upgrade head
uv run python dev.py
```

In a second terminal, from the project root:

```sh
npm --prefix frontend run dev
```

Open the URL printed by Vite, normally [localhost:5173](http://localhost:5173),
and click **ตรวจสอบ Backend**. Vite forwards the request to FastAPI, which
runs a read-only database query. FastAPI's interactive API docs are at
[localhost:8000/docs](http://localhost:8000/docs).

## Checks

Run these commands from the project root:

```sh
npm run build
npm --prefix frontend run lint
curl -fsS http://localhost:5173/api/health/db
```

With both servers running and the database configured, the last command returns
`{"status":"ok","database":"connected"}`.

## Project structure and status

- `frontend/` contains the React app and Vite proxy configuration.
- `backend/` contains FastAPI, the SQLAlchemy models, and Alembic migrations.
- `neon.ts` defines the Neon branch configuration.

The initial migration creates `users`, `resources`, `availability_rules`, and
`bookings`. Login, booking APIs and screens, concurrent booking protection,
image storage, and natural-language booking are planned work.
