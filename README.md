# Trinity Roots Room Booking

Find and reserve meeting rooms by date and group size, using a form or an AI assistant in Thai or English. View, change, and cancel your own reservations in **My bookings**.

Built with **React + TypeScript**, **FastAPI**, and **Neon PostgreSQL**. SQLAlchemy defines the models, Psycopg connects to PostgreSQL, and Alembic manages migrations. The LLM key stays on the backend.

## Features

- Ten rooms with photos and capacities; book one or more hourly slots between **08:00 and 18:00 Bangkok time**.
- Optional projectors, cameras, and microphones, reserved for the room's selected slots.
- Owner-only edits and cancellation, with database protection against overlapping room and equipment bookings.
- AI proposals that require confirmation, plus **conflict suggestions** checked by the backend before display.
- Sensitive-data masking, model request/response logs, and a normal booking form that works without the LLM.

## Quick start

Use **Node.js 24.16.0**, **Python 3.12.16**, npm, uv, and a Neon PostgreSQL database. An OpenAI key is optional for the form and required for chat. See [full setup instructions](docs/setup.md) for pip installation, settings, ports, and startup behavior.

**1. Install dependencies** from the project root:

```sh
npm ci
npm --prefix frontend ci
uv sync --project backend --locked
```

**2. Create `.env.local`** in the project root, using pooled and direct URLs from the same Neon branch and database. Keep their SSL parameters.

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@POOLED_HOST/DB?sslmode=require
DATABASE_URL_UNPOOLED=postgresql://USER:PASSWORD@DIRECT_HOST/DB?sslmode=require
# OPENAI_API_KEY=your-openai-api-key
# OPENAI_MODEL=gpt-6-luna
# SESSION_SECRET=replace-with-a-long-random-value
```

Uncomment `OPENAI_API_KEY` to enable chat. A fixed `SESSION_SECRET` preserves login sessions across backend restarts. These local settings are ignored by Git.

**3. Apply migrations and seed the catalog:** the database role must be able to enable `btree_gist`.

```sh
cd backend
uv run alembic upgrade head
uv run python seed_rooms.py
uv run python seed_equipment.py
cd ..
```

**4. Start both servers with one command:**

```sh
npm run dev
```

Open the [app](http://127.0.0.1:5173), create an account, and sign in. [FastAPI docs](http://127.0.0.1:8000/docs) list the API endpoints. Press **Ctrl+C** to stop both servers.

## Tests

After installing dependencies, start Docker and run:

```sh
npm test
```

This runs **21 pytest API/database cases and 4 Cypress UI cases**, without an LLM key or running app servers. API tests use real PostgreSQL migrations and separate connections to check concurrent bookings and rollback; model responses are mocked. Cypress checks UI behavior with stubbed API responses. These tests do not measure real model quality or production load. See [test cases](tests/README.md) and [testing details](docs/development.md#check-the-app).

Python runtime and development dependencies are also available in [requirements.txt](requirements.txt), exported from [backend/uv.lock](backend/uv.lock).

## Design decisions and trade-offs

| Decision | Why | Trade-off |
| --- | --- | --- |
| **PostgreSQL exclusion constraints and transactions** | Reject overlapping room/equipment bookings even during simultaneous requests, and roll back the whole operation on conflict. | GiST and multirange storage make this design PostgreSQL-specific. |
| **One reservation for room, slots and equipment** | Users edit or cancel the whole reservation together. Removing a slot releases both room and equipment. | Equipment requires a room, uses exactly its selected slots, and is limited to one unit per type. |
| **Structured AI tools with user confirmation** | The model proposes a tool and arguments. FastAPI validates them, and only the user's confirmation submits a write. | Valid arguments can still reflect a misunderstood request, so users must review the proposal. |
| **Availability polling every five seconds** | Reuse the existing API without adding live-update infrastructure. | Displayed availability can become stale before confirmation. The database remains the final check. |
| **Per-account limits in memory** | Limit chat and alternative requests to 10 per rolling 60 seconds without another service. | Counters reset on restart and are not shared between backend workers. |

Signed HttpOnly cookies identify accounts. The backend scopes booking lists and checks ownership before edits or cancellation; it does not trust an account ID from the model. [More design details](docs/design.md)

## Additional feature: conflict suggestions

When a requested room or equipment is unavailable, the chat asks whether to keep the same time, keep the same room, or allow either. This also handles someone booking first while a proposal is being reviewed. The backend builds up to 12 valid candidates, the model chooses up to three, and the backend checks every selected option again before showing it.

Alternatives keep the date, group size, equipment, duration and gaps. The user must select and confirm again. No matching option means asking for another preference, not silently changing it. Suggestions do not hold resources, so another conflict is still possible at confirmation.

This is the chosen additional feature. MCP, an evaluation harness and Laya are not included to keep the submission focused. OpenAI tool calling already covers the current decisions; adding Laya would require another integration and evaluation effort. [Suggestion logic and limits](docs/design.md#how-conflict-suggestions-work)

## Guardrails, logs and failure handling

Microsoft Presidio masks detected Thai national IDs, phone numbers, emails and known or explicitly labelled API keys with `[REDACTED]` before sending user text to the model. Instructions treat messages as untrusted and restrict the assistant to booking tools. Pydantic validates tool arguments, and the backend checks business rules rather than executing arbitrary model output.

**Guardrails cannot catch everything:** patterns may miss spelled-out numbers, unusual formats, unfamiliar unlabelled keys, names and addresses, or hide harmless matching text. Prompt injection can still influence allowed arguments or rankings. User confirmation provides a chance to catch mistakes; it is not a guarantee of correct intent.

The root `.assistant-audit.jsonl` stores the exact masked request and received response bodies, including tool calls and API errors, paired by `request_id`. It is Git-ignored with owner-only permissions (`0600`). Headers are excluded. Missed identifiers and unmasked model responses may remain in the log; automatic retention and rotation are not implemented. A network failure can leave a request without a response.

Chat and alternative-selection clients use 15- and 12-second timeouts with retries disabled. Provider errors or invalid model arguments return an error instead of creating a booking. The normal form calls the booking API directly and remains usable when only the LLM is unavailable. [Guardrail and failure-handling details](docs/design.md#assistant-guardrails-and-logs)

## Assumptions and intentional limits

- **Scheduling:** one room and date per booking, with hourly slots from 08:00 to 18:00 Bangkok time. Shared hours keep validation simple; holidays, recurring bookings and schedules per room are omitted.
- **Lifecycle:** confirmation creates a `confirmed` booking. Owners can edit or cancel before its first slot starts. Automatic `completed` transitions are omitted to avoid a background scheduler. A room change requires a new booking and a separate cancellation.
- **Chat and catalog:** page-local history and bundled room images avoid a conversation store and upload service. Reloading clears chat; uploads are not supported. Group size is checked at creation but not stored on the booking.
- **Suggestion scope:** alternatives support new chat bookings. Conflicting edits retain the old reservation and require a manual change. Waitlists and automatic rebooking are omitted to keep approval explicit.

These choices keep the exercise focused on reliable booking and reviewed AI actions. [Full scope and limitations](docs/design.md#current-scope-and-limitations)

## Detailed documentation

| Read more | Contents |
| --- | --- |
| [Setup](docs/setup.md) | Exact installation steps, environment variables, migrations, seed data, and startup |
| [User guide](docs/usage.md) | Form and AI booking, equipment, edits, cancellation, and preference choices |
| [Design and safeguards](docs/design.md) | Assumptions, transactions, guardrails, logs, conflict-suggestion logic, trade-offs, and why Laya is omitted |
| [Development and testing](docs/development.md) | Test commands and isolation, dependencies, checks, and project structure |
| [Test cases](tests/README.md) | API and UI scenarios with expected results and implementation links |
| [Data model and booking flows](docs/diagrams.md) | ER diagram and sequence diagrams for form booking, AI booking, and conflicts |
