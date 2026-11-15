# Trinity Roots Room Booking

Find and reserve meeting rooms by date and group size. Use the booking form or ask the AI assistant in Thai or English. Open **My bookings** to view, move, or cancel your own reservations.

The app uses React and TypeScript for the interface, FastAPI for the API, and Neon PostgreSQL for storage. SQLAlchemy defines the database models, Psycopg 3 connects to PostgreSQL, and Alembic manages schema changes. FastAPI holds the OpenAI API key and makes the model calls.

## Run locally

You'll need Node.js 24 with npm, Python 3.12 with uv, and a Neon PostgreSQL database. Development uses Node.js **24.16.0** and Python **3.12.16**. An OpenAI API key enables chat. The booking form works without one. [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### 1. Install dependencies

Run these commands from the project root.

```sh
npm ci
npm --prefix frontend ci
uv sync --project backend --locked
```

### 2. Configure the environment

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

### 3. Set up the database and start FastAPI

In the first terminal, run these commands from the project root. The database role needs permission to run the migrations, including enabling `btree_gist`.

```sh
cd backend
uv run alembic upgrade head
uv run python seed_rooms.py
uv run python seed_equipment.py
uv run python dev.py
```

The seed scripts add 10 rooms with capacities and photo references, plus 8 projectors, 5 cameras, and 5 microphones. They can be rerun to add missing entries and fill missing room capacities.

### 4. Start React

In a second terminal, run this command from the project root.

```sh
npm --prefix frontend run dev
```

Open the URL Vite prints, usually [localhost:5173](http://localhost:5173). Choose **Create account**, then sign in. Vite forwards `/api` requests to FastAPI on port 8000. Keep both terminals running while using the app. [FastAPI API docs](http://localhost:8000/docs)

## Book a room

1. Click **Book now** and enter a date and group size. The page shows rooms that fit your group and refreshes availability about every five seconds.
2. Pick one or more one-hour slots in the same room on the same day, then confirm. Rooms can be booked daily from **08:00 to 18:00 Bangkok time**. Each slot must start in the future and on the hour.
3. Open **My bookings** to see your reservations. Use **Edit booking** to change the day or time of one upcoming slot in the same room, then **Save changes**. Use **Cancel booking** and confirm to release a slot.

The assistant is on the booking page. On mobile, tap **Ask AI**. Try **“Book a room for 8 tomorrow from 10:00 to 12:00”** or **“จองห้องสำหรับ 8 คน พรุ่งนี้ 10:00–12:00”**. The backend finds a room free for the whole period and shows a proposal. Review it, then click **Confirm booking**. The slots are reserved when confirmation succeeds, after another availability check.

When a request gives only a start time, the assistant assumes one hour. When no room is named, the backend chooses the smallest available room that fits the group. A request for a large room selects the largest suitable room.

## How bookings stay consistent

If two users try to book the same room and time, PostgreSQL's `bookings_no_overlap` constraint lets only one succeed. It also protects edits. Time ranges include the start and exclude the end, so **08:00–09:00** and **09:00–10:00** can both be booked.

All slots in a new booking are saved in one transaction. If any slot conflicts, the whole transaction rolls back and returns **409 Conflict**. A conflicting edit preserves the original reservation. Edits and cancellations lock the booking row while updating it.

Bookings start as `confirmed` after the user confirms. The owner can edit or cancel them before they start, and cancellation changes the status to `cancelled`. The schema allows `completed`, but elapsed bookings currently keep their existing status. This keeps the workflow simple without a scheduled status-update job.

Passwords are hashed with Argon2. A signed HttpOnly cookie identifies the account on each request, and the backend checks ownership before changing a booking.

## Design decisions and trade-offs

| Decision | Why it works for this app | Trade-off |
| --- | --- | --- |
| **Database conflict checks** | The database enforces one rule even when several requests arrive together. | The GiST constraint and `btree_gist` extension tie this design to PostgreSQL. |
| **One record per hour** | Users can move or cancel one hour of a longer booking. | A two-hour booking appears as two records and takes two edits to move. Partial-hour bookings are outside the current scope. |
| **Availability polling** | The page refreshes using the existing HTTP API about every five seconds. | It sends repeated requests and can briefly show an outdated slot. |
| **AI proposals with user confirmation** | The user reviews the details, and chat shares the form's booking API. | Confirmation adds a step, and availability can change during review. |
| **In-memory rate limits** | Each account gets 10 chat requests per rolling 60 seconds without another storage service. | Counts reset on restart and are separate for each worker. |

## Assistant guardrails and logs

Microsoft Presidio pattern recognizers detect Thai national ID numbers, common Thai mobile and landline numbers, email addresses, and known or explicitly labelled API keys. The anonymizer replaces matches with `[REDACTED]` before each user message in the model request is sent.

The model receives instructions to treat messages as untrusted and stay within room booking. It returns a structured tool call for `search_rooms`, `propose_room_booking`, or `clarify_room_search`. FastAPI validates the arguments with Pydantic, runs the allowed action, and builds the reply. The user approves a proposal through **Confirm booking**, which calls the regular booking API.

The project-root file `.assistant-audit.jsonl` records the exact JSON request body sent to OpenAI after masking and the response body received, including tool calls and API errors. Match entries by `request_id`. Each has a timestamp, `event`, and a `body` containing a JSON string. The response log captures the model's tool call, which FastAPI uses to build the on-screen reply.

The file is created with owner-only read/write permissions (`0600`) and ignored by Git. HTTP headers and pre-mask messages are excluded. A network failure can leave a request with no matching response.

### Guardrail trade-offs

- **Pattern-based masking** gives us explicit rules for common Thai identifiers and key formats. It can miss spelled-out numbers, unusual formats, unlabelled keys with unfamiliar prefixes, and details such as names or addresses. It can also hide harmless text that matches a pattern, leaving the model with less context.
- **Limited tools and backend-generated replies** restrict the actions available to the model. A prompt injection can still steer it toward the wrong allowed tool or valid but unwanted arguments. User confirmation gives a chance to catch those errors. The rules also make replies less flexible, and the model can misread ordinary dates or group sizes.
- **Exact request and response logs** help debug a bad result, but missed identifiers and model responses can contain personal data. The log needs restricted access and a retention policy. Automatic log rotation and deletion are pending.

### When the assistant fails

The OpenAI client uses a 15-second timeout with automatic retries disabled. Model errors or invalid tool arguments produce an error message, and users can continue with the booking form. Exceeding the app's chat quota returns **429** with a `Retry-After` header. The quota counts requests per account within each FastAPI process.

## Check the app

Run these commands from the project root to build and lint the frontend.

```sh
npm run build
npm --prefix frontend run lint
```

With both servers running, check the database connection through the frontend proxy. Use Vite's printed port if it differs from 5173.

```sh
curl -fsS http://localhost:5173/api/health/db
```

A successful response is `{"status":"ok","database":"connected"}`. This checks connectivity. Automated booking, concurrency, and assistant tests are still pending.

## Project structure

| Location | Purpose |
| --- | --- |
| `frontend/src/` | React pages, booking forms, and the assistant panel |
| `backend/bookings.py` | Availability, creation, rescheduling, and cancellation |
| `backend/assistant.py` | Model calls, tools, and chat rate limits |
| `backend/assistant_privacy.py` | Masking and request/response logs |
| `backend/auth.py` | Registration, login, and account checks |
| `backend/models.py` and `backend/migrations/` | Database models and schema history |
| `neon.ts` | Neon branch configuration |

The four application tables are `users`, `resources`, `bookings`, and `availability_rules`. Room capacity is stored in `resources`. Opening hours currently come from `backend/availability.py`. The `availability_rules` table is reserved for future schedules per resource.

## Current scope

- Development currently focuses on room booking. Equipment can be browsed, and equipment reservations are pending.
- All rooms share daily Bangkok opening hours. Holidays and schedules per room are outside the current scope.
- Room photos ship with the frontend to keep setup simple. Uploads and external image storage are outside the current scope.
- Chat handles new bookings. Edits and cancellations use **My bookings** and its existing ownership checks.
- Chat history lives in the browser page, and recent user messages provide follow-up context. Reloading the page clears the conversation.
- The exercise still needs automated tests that run without an LLM key, one command to start both servers, and at least one additional feature. The options are an MCP server, conflict suggestions checked by the backend, an evaluation harness, or typed decisions built on Laya.
