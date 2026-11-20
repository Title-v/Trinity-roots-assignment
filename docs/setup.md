# Setup

[Back to README](../README.md)

You'll need Node.js 24 with npm, Python 3.12 with uv, and a Neon PostgreSQL database. Development uses Node.js **24.16.0** and Python **3.12.16**. An OpenAI API key enables chat. The booking form works without one. [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

## 1. Install dependencies

Run these commands from the project root.

```sh
npm ci
npm --prefix frontend ci
uv sync --project backend --locked
```

These commands also install pytest and Cypress. To run the API tests, install and start Docker separately; see [test tool installation](development.md#install-test-tools). UI-only tests do not require Docker or the database setup below.

Python dependencies are declared in `backend/pyproject.toml` and pinned in `backend/uv.lock`. The root `requirements.txt` contains the same locked runtime and development dependencies, including pytest. If you use pip in an activated Python 3.12 environment, install them with:

```sh
python -m pip install -r requirements.txt
```

The npm commands below still use uv for Python execution. After changing Python dependencies, regenerate the pip export instead of editing versions by hand:

```sh
uv export --project backend --locked --no-emit-project --no-hashes --no-annotate --output-file requirements.txt
```

## 2. Configure the environment

Create `.env.local` in the project root. Copy both connection strings from the **same Neon branch and database**, keeping their SSL parameters. FastAPI uses the pooled URL, and Alembic uses the direct URL for migrations.

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@POOLED_HOST/DB?sslmode=require
DATABASE_URL_UNPOOLED=postgresql://USER:PASSWORD@DIRECT_HOST/DB?sslmode=require

# Optional settings
# OPENAI_API_KEY=your-openai-api-key
# OPENAI_MODEL=gpt-6-luna
# SESSION_SECRET=replace-with-a-long-random-value
```

Uncomment `OPENAI_API_KEY` and supply your key to enable the assistant. `OPENAI_MODEL` overrides the default model, `gpt-6-luna`. A fixed `SESSION_SECRET` keeps sessions valid across backend restarts. If it is omitted, the backend generates a secret on startup and users must sign in again after a restart. Git ignores local environment files.

## 3. Set up the database

Run these commands from the project root to apply migrations and load the sample catalog. The database role needs permission to run the migrations, including enabling `btree_gist`.

```sh
cd backend
uv run alembic upgrade head
uv run python seed_rooms.py
uv run python seed_equipment.py
cd ..
```

The seed scripts add 10 rooms with capacities and photo references, plus 8 projectors, 5 cameras, and 5 microphones. They can be rerun to add missing entries and fill missing room capacities.

## 4. Start the app

After setup, start both servers with one command from the project root.

```sh
npm run dev
```

React runs on port **5173**, and FastAPI runs on port **8000**. Open the app, choose **Create account**, then sign in. Vite forwards `/api` requests to FastAPI. [Open the app](http://127.0.0.1:5173) · [FastAPI API docs](http://127.0.0.1:8000/docs)

Keep this terminal open while using the app. Logs are labelled `api` and `web`. Press **Ctrl+C** once to stop both servers. If either server exits, the other is stopped too. Both use fixed ports, so startup reports an error if either port is already occupied.
