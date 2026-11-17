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

### 3. Set up the database

Run these commands from the project root to apply migrations and load the sample catalog. The database role needs permission to run the migrations, including enabling `btree_gist`.

```sh
cd backend
uv run alembic upgrade head
uv run python seed_rooms.py
uv run python seed_equipment.py
cd ..
```

The seed scripts add 10 rooms with capacities and photo references, plus 8 projectors, 5 cameras, and 5 microphones. They can be rerun to add missing entries and fill missing room capacities.

### 4. Start the app

After setup, start both servers with one command from the project root.

```sh
npm run dev
```

React runs on port **5173**, and FastAPI runs on port **8000**. Open the app, choose **Create account**, then sign in. Vite forwards `/api` requests to FastAPI. [Open the app](http://127.0.0.1:5173) · [FastAPI API docs](http://127.0.0.1:8000/docs)

Keep this terminal open while using the app. Logs are labelled `api` and `web`. Press **Ctrl+C** once to stop both servers. If either server exits, the other is stopped too. Both use fixed ports, so startup reports an error if either port is already occupied.

## Book a room

1. Click **Book now** and enter a date and group size. The page shows rooms that fit your group and refreshes availability about every five seconds.
2. Pick one or more one-hour slots in the same room on the same day. Optionally tick **Projector**, **Camera**, or **Microphone** to reserve one unit of each selected type for all those slots, then confirm. The checkboxes show how many units are available for the whole selection. Rooms can be booked daily from **08:00 to 18:00 Bangkok time**. Each slot must start in the future and on the hour.
3. Open **My bookings** to see your reservations and assigned equipment. All selected slots appear in one booking. Use **Edit booking** to change the date, time slots, or equipment, then **Save changes**. Cancellation releases the room and all its equipment together.

The assistant is on the booking page. On mobile, tap **Ask AI**. Try **“Book a room for 8 with a projector tomorrow from 10:00 to 12:00”** or **“จองห้องสำหรับ 8 คน พร้อมโปรเจคเตอร์ พรุ่งนี้ 10:00–12:00”**. The backend checks the full time period and requested equipment, then shows matching rooms with photos and capacities. Select a room, review its date, time, and equipment, then click **Confirm booking**. The slots and equipment are reserved when confirmation succeeds, after another availability check.

For a new booking, the assistant asks for a missing start or end time before showing rooms. An explicit duration, such as two hours, lets it calculate the end time from the stated start. Matching rooms are ordered by capacity, starting with the smallest that fits the group. A request for a large room puts the largest choices first. The user selects the room before confirming.

Before preparing a new booking, the chat asks whether equipment is needed if the user has not stated a preference. Reply with the equipment names or say **“ไม่ต้องการ”** / **“no equipment”**. The assistant keeps the date, time, and group size from the conversation. An equipment choice or an explicit decline in the initial request lets the chat proceed directly to room selection.

The equipment answer applies to the current booking. After confirmation or discarding a draft, the next request starts with fresh context, while previous messages remain visible in the chat.

To manage an existing booking, try **“Show my bookings”**, **“เลื่อนการจองของฉันเป็นพรุ่งนี้ 13:00–15:00 แล้วเพิ่มกล้อง”**, or **“Cancel my booking”**. The chat shows your own matching reservations. Select one, review or adjust the proposed date, time slots, and equipment, then click **Confirm changes** or **Confirm cancellation**. These buttons use the same booking APIs as **My bookings**. Changes are saved after confirmation.

If you give only a new start time, the edit form shifts the existing slots together, preserving their duration and gaps. You can adjust the proposed slots before confirming. Adding or removing equipment keeps the other selected types.

## Booking assumptions

- **Equipment belongs to a room booking.** Users can select equipment when booking a room or add it to their own upcoming confirmed room booking. This keeps the room and its equipment under one reservation that the user can manage together.
- **Equipment uses exactly the room's selected time slots.** For example, a room booked from 10:00 to 12:00 reserves its projector for 10:00 to 12:00 too. Changing the room's date or time slots moves the equipment with it. Removing a time slot releases both the room and its equipment for that period.
- **Cancelling the room automatically cancels all linked equipment.** One confirmation releases every reserved time slot and equipment unit in that booking.

The backend saves these changes in one transaction. If the room or selected equipment is unavailable, it rolls back the whole operation. A failed edit preserves the previous room and equipment reservations.

## How bookings stay consistent

If two users try to book the same room and time, PostgreSQL's `bookings_no_overlap` constraint lets only one succeed. It also protects edits. Each booking stores its selected periods in a `tstzmultirange` column. This supports both adjacent and separated slots. For example, selecting **08:00–09:00** and **10:00–11:00** leaves **09:00–10:00** available. Range boundaries allow back-to-back bookings.

All slots in a new booking are saved in one transaction. If any slot conflicts, the whole transaction rolls back and returns **409 Conflict**. A conflicting edit preserves the original reservation. Edits and cancellations lock the booking row while updating it.

Equipment is shared across rooms. The backend assigns an available physical unit of each selected type. Inventory rows are locked in a consistent order during allocation, and a database constraint prevents overlapping reservations for the same unit. Room and equipment changes commit together. If equipment runs out, the whole operation rolls back.

Bookings start as `confirmed` after the user confirms. The owner can edit or cancel them before they start, and cancellation changes the status to `cancelled`. The schema allows `completed`, but elapsed bookings currently keep their existing status. This keeps the workflow simple without a scheduled status-update job.

Passwords are hashed with Argon2. A signed HttpOnly cookie identifies the account on each request, and the backend checks ownership before changing a booking.

## Design decisions and trade-offs

| Decision | Why it works for this app | Trade-off |
| --- | --- | --- |
| **Database conflict checks** | The database enforces one rule even when several requests arrive together. | The GiST constraint and `btree_gist` extension tie this design to PostgreSQL. |
| **One booking for all selected slots** | A two-hour selection creates one booking that can be moved or cancelled together. Users can add or remove hourly slots when editing. | The PostgreSQL multirange type ties the storage format to PostgreSQL. A booking can be edited or cancelled before its first slot starts. |
| **Availability polling** | The page refreshes using the existing HTTP API about every five seconds. | It sends repeated requests and can briefly show an outdated slot. |
| **AI proposals with user confirmation** | The user reviews the details, and chat shares the form's booking API. | Confirmation adds a step, and availability can change during review. |
| **In-memory rate limits** | Each account gets 10 chat requests per rolling 60 seconds without another storage service. | Counts reset on restart and are separate for each worker. |
| **Equipment follows the room booking** | Users manage one reservation. Changing the room's times moves its equipment too, and cancelling the room releases everything together. | Equipment requires a room booking and uses all its selected time slots, even when needed for only part of the meeting. Keeping equipment after cancelling the room would require a separate borrowing flow. |
| **Automatic equipment allocation** | Users choose a type, and the backend finds one unit available throughout the booking. | Each checkbox reserves one unit. Requests using the same equipment category briefly wait for inventory locks. |

## Assistant guardrails and logs

Microsoft Presidio pattern recognizers detect Thai national ID numbers, common Thai mobile and landline numbers, email addresses, and known or explicitly labelled API keys. The anonymizer replaces matches with `[REDACTED]` before each user message in the model request is sent.

The model receives instructions to treat messages as untrusted and stay within room booking. It returns a structured tool call for `search_rooms`, `propose_room_booking`, `manage_my_bookings`, or `clarify_room_search`. FastAPI validates the arguments with Pydantic and prepares the results for review. Booking lists are scoped to the account from the session cookie. The user submits a write through **Confirm booking**, **Confirm changes**, or **Confirm cancellation**, and the normal booking API checks ownership, time rules, and availability.

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

With `npm run dev` running, check the database connection through the frontend proxy.

```sh
curl -fsS http://127.0.0.1:5173/api/health/db
```

A successful response is `{"status":"ok","database":"connected"}`. This checks connectivity.

## Project structure

| Location | Purpose |
| --- | --- |
| `frontend/src/` | React pages, booking forms, and the assistant panel |
| `backend/bookings.py` | Availability, creation, rescheduling, and cancellation |
| `backend/assistant.py` | Model calls, tools, and chat rate limits |
| `backend/booking_alternatives.py` | Build alternative bookings, ask the model to select them, and recheck availability |
| `backend/assistant_privacy.py` | Masking and request/response logs |
| `backend/auth.py` | Registration, login, and account checks |
| `backend/models.py` and `backend/migrations/` | Database models and schema history |
| `neon.ts` | Neon branch configuration |

The application tables are `users`, `resources`, `bookings`, `booking_equipment`, and `availability_rules`. Room capacity and individual equipment units are stored in `resources`. `booking_equipment` links assigned units to a room booking and records their reserved periods. Opening hours currently come from `backend/availability.py`. The `availability_rules` table is reserved for future schedules per resource.

The time-range migration backfills existing bookings with their original periods. Earlier bookings keep their individual IDs. New selections are saved together as one booking.

## Current scope

- Each equipment checkbox reserves one unit of that type for the room booking.
- All rooms share daily Bangkok opening hours. Holidays and schedules per room are outside the current scope.
- Room photos ship with the frontend to keep setup simple. Uploads and external image storage are outside the current scope.
- Chat manages one booking per confirmation. Edits cover dates, time slots, and equipment within the same room. A change of room uses a new booking followed by cancellation of the original reservation.
- Chat history lives in the browser page, and recent user messages provide follow-up context. Reloading the page clears the conversation.
- The exercise still needs automated tests that run without an LLM key. Conflict suggestions are implemented as the additional feature.

## Conflict suggestions

This feature helps when a requested room or equipment is unavailable, including when someone else books it while you are reviewing a chat proposal. It applies to new chat bookings. A conflicting edit keeps the original reservation and requires a new selection.

### What the user sees

For example, you request **Oak Room, 14:00–16:00, for 5 people**. Someone else confirms that room before you do. Your confirmation returns **409 Conflict**, so your booking is not created. The chat keeps your requested details and asks what you want to keep:

| Choice | What may change | What stays fixed |
| --- | --- | --- |
| **Same time** | The room | Every selected time slot |
| **Same room** | The time | The selected room |
| **Either** | The room and time | The date, group size, equipment, and total duration |

The date, group size, equipment, and total duration stay fixed for all three choices. “Same room” is available only when a room has been named or selected.

You can press a button or give a short answer such as “same time”, “same room”, or “either”, also supported in Thai. Ambiguous answers ask you to use the buttons. To change the date or other requirements, choose **New search**.

If you choose **Same time**, the chat might offer Lotus Room from 14:00–16:00. If you choose **Same room**, it might offer Oak Room from 12:00–14:00 or 16:00–18:00. These are examples, not guaranteed availability.

Each option shows a room photo, capacity, date, and time. You must select an option and press **Confirm booking** again. Choosing a preference does not create a booking.

### How it works

1. **Ask before finding alternatives.** The chat waits for your preference. After a failed confirmation, it asks again instead of silently changing the room or time. The preference is sent to the authenticated, rate-limited `POST /assistant/alternatives` endpoint with the original booking details and recent user messages.
2. **Build valid candidates.** `find_booking_alternatives()` reads room availability from PostgreSQL. It checks active rooms, capacity, future time slots within 08:00–18:00 Bangkok time, and equipment available for the entire booking. It excludes the failed room-and-time combination. If time changes are allowed, it shifts the selected slots together in one-hour steps on the same date, preserving duration and any gaps.
3. **Apply the preference and limit the list.** “Same time” removes other times; “Same room” removes other rooms. The backend orders the remaining options by unchanged time, distance from the original time, original room, and capacity preference. It passes at most 12 candidates to the model, each with a local ID such as `choice_1`.
4. **Let the model select suggestions.** `suggest_booking_alternatives()` sends the explicit preference, recent masked user messages, and candidate details to the model. The model selects up to three IDs through a structured tool call. It uses the conversation to choose useful options within the allowed list; it cannot invent room IDs or time slots. The backend validates the returned IDs and removes duplicates.
5. **Check again before display.** `verify_booking_alternatives()` reloads availability and checks each selected option against the preference, room capacity, business hours, future times, and equipment stock. An option taken while the model was responding is dropped. Only verified options reach the user.
6. **Check again when confirming.** The existing booking API creates the reservation. PostgreSQL exclusion constraints remain the final protection against overlapping requests. If someone takes the new option first, confirmation fails and the chat asks for your preference again.

The backend decides what is possible. The model selects which valid options to recommend using the user's preference and conversation context. The model does not write bookings to the database. Ranking requests and responses use the same masking and audit logging as other assistant calls.

### Trade-offs and limits

- **Preferences are strict.** If no room is free at the requested time, choosing “Same time” returns no alternatives. The system does not silently offer a different time. You can choose another preference or start a new search.
- **The search stays on the same day.** It preserves equipment and total duration, so it may find nothing even when a shorter booking, different equipment, or another day would work.
- **The candidate list is bounded.** Sending at most 12 options keeps the model request smaller, but can omit useful options. The model chooses only from this shortlist, and its ranking may vary between calls.
- **The model adds latency and a dependency.** Backend rules could choose three options directly. Here the model uses conversation context to select recommendations, as required by the exercise. If the lookup fails, the UI offers a retry and the normal booking form remains available.
- **A suggestion is not a reservation.** Availability can change after the final check. Only successful confirmation reserves the room and equipment. If all selected suggestions become unavailable before display, the UI reports no verified alternatives instead of showing stale options.
