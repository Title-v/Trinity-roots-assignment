# Design, safeguards and trade-offs

[Back to README](../README.md)

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

| Decision | Benefit | Trade-off |
| --- | --- | --- |
| **PostgreSQL conflict constraints** | Room and equipment overlaps are rejected even when requests arrive together. | GiST, `btree_gist`, and multirange storage tie the design to PostgreSQL. |
| **One booking for multiple hourly slots** | Adjacent or separated slots can be edited and cancelled together. | All slots must belong to one room and date. The entire booking becomes uneditable once its first slot starts. |
| **Availability polling** | Room and equipment availability refresh through existing APIs about every five seconds. | Polling adds requests, can show stale data, and does not hold a selected slot. |
| **AI proposals with explicit confirmation** | Chat and forms use the same booking API and backend rules. | Review adds a step. A proposal can become unavailable before confirmation. |
| **Ask before suggesting alternatives** | Users choose whether to keep the time, room, or neither before the model selects options. | Conflicts require another answer and confirmation. Strict preferences may leave no alternatives. |
| **Recent chat context in the browser** | Short follow-ups work without a server-side chat-session database. | Only recent context is sent to the model, and reloading clears the chat. Older details may be lost. |
| **In-memory assistant quota** | Chat and alternative lookups share a limit of 10 requests per account per rolling 60 seconds. | Counts reset on restart and are separate for each worker, so this is not a distributed limit. |
| **Equipment follows the room** | Room and equipment changes commit or roll back together. Cancellation releases both. | Equipment cannot be booked alone or for only part of the room's selected time slots. |
| **Automatic equipment allocation** | Users choose a type and the backend finds a free physical unit. | Only one unit per type is supported. Users cannot choose a specific unit, and competing allocations wait for inventory locks. |

### Why Laya is not included

OpenAI tool calling already handles the decisions this app needs: selecting a booking tool, extracting its arguments, and choosing alternative candidate IDs. Tool schemas and enums constrain the outputs; the backend still checks business rules and availability, and users confirm every write.

Adding Laya for these same decisions would introduce another model integration and evaluation effort. This version therefore uses **Conflict suggestions** as its additional feature and does not add Laya. The trade-off is continued dependence on the OpenAI service. A separate decision model would be worth considering if measurements showed a benefit for a specific task.

## Assistant guardrails and logs

**Masking:** Microsoft Presidio replaces detected Thai national IDs, common Thai mobile/landline numbers, emails, and known or explicitly labelled API keys with `[REDACTED]` before sending user text to the model.

**Controlled actions:** The model is instructed to treat messages as untrusted and use booking tools. Pydantic validates tool arguments; FastAPI builds the replies and scopes booking lists to the signed-in account. Creating, editing, or cancelling a booking requires user confirmation, followed by backend checks for ownership, time rules, and availability. Alternative suggestions are also checked before display.

**Audit logs:** `.assistant-audit.jsonl` in the project root stores the exact masked request and received response bodies, including tool calls and API errors. Entries contain a timestamp, `event`, `request_id`, and a JSON-string `body`. Pair requests and responses by `request_id`; a network failure may leave a request without a response. The local file uses owner-only permissions (`0600`) and is Git-ignored. Vercel uses the private `assistant_audit_logs` database table for durable storage. Headers and pre-mask text are not logged. See [deployment details](deployment.md#audit-logs).

### Guardrail trade-offs

- **Masking is pattern-based:** It can miss spelled-out numbers, unusual formats, unfamiliar unlabelled keys, names, and addresses. False matches can remove useful context, including context used to rank alternatives.
- **Validation is not intent detection:** Pydantic, allowed tools, and candidate IDs constrain outputs but cannot guarantee the model understood the user. Prompt injection may still influence allowed arguments or rankings. Fixed replies and explicit confirmation reduce flexibility but give users a chance to catch mistakes.
- **Exact logs retain risk:** Model responses are logged as received, without a second masking pass. Missed identifiers may remain. Local file permissions restrict access, but automatic retention, rotation, and deletion are not implemented.

### When the assistant fails

The OpenAI clients use a **15-second timeout for chat** and **12 seconds for alternative selection**, with automatic retries disabled. The frontend stops waiting for either assistant endpoint after 40 seconds. Provider errors, invalid model arguments, or audit-log failures return **503**. Alternative lookup failures offer a retry, and the normal booking form remains usable without an LLM key.

Both assistant endpoints share the per-account quota. Exceeding it returns **429** with `Retry-After`; accepted requests count even if the later model call fails. These controls apply within each FastAPI process, not across multiple workers.

## How conflict suggestions work

1. **Ask before finding alternatives.** The chat waits for your preference. After a failed confirmation, it asks again instead of silently changing the room or time. The preference is sent to the authenticated, rate-limited `POST /assistant/alternatives` endpoint with the original booking details and recent user messages.
2. **Build valid candidates.** `find_booking_alternatives()` reads room availability from PostgreSQL. It checks active rooms, capacity, future time slots within 08:00–18:00 Bangkok time, and equipment available for the entire booking. It excludes the failed room-and-time combination. If time changes are allowed, it shifts the selected slots together in one-hour steps on the same date, preserving duration and any gaps.
3. **Apply the preference and limit the list.** “Same time” removes other times; “Same room” removes other rooms. The backend orders the remaining options by unchanged time, distance from the original time, original room, and capacity preference. It passes at most 12 candidates to the model, each with a local ID such as `choice_1`.
4. **Let the model select suggestions.** `suggest_booking_alternatives()` sends the explicit preference, recent masked user messages, and candidate details to the model. The model selects up to three IDs through a structured tool call. It uses the conversation to choose useful options within the allowed list; it cannot invent room IDs or time slots. The backend validates the returned IDs and removes duplicates.
5. **Check again before display.** `verify_booking_alternatives()` reloads availability and checks each selected option against the preference, room capacity, business hours, future times, and equipment stock. An option taken while the model was responding is dropped. Only verified options reach the user.
6. **Check again when confirming.** The existing booking API creates the reservation. PostgreSQL exclusion constraints remain the final protection against overlapping requests. If someone takes the new option first, confirmation fails and the chat asks for your preference again.

The backend decides what is possible. The model selects which valid options to recommend using the user's preference and conversation context. The model does not write bookings to the database. Ranking requests and responses use the same masking and audit logging as other assistant calls.

### Conflict suggestion trade-offs

- **Explicit preference, limited phrasing:** Buttons and recognized short Thai/English answers set a hard constraint: same time, same room, or either. This avoids guessing, but the preference step is not an open-ended conversation. Unrecognized answers ask the user to use the buttons or start a new search.
- **Preserve the request:** Alternatives keep the date, group size, equipment, duration, and gaps. Time changes use one-hour steps. This keeps choices comparable but excludes options on another day, shorter bookings, or different equipment. “Either” relaxes only the room and time.
- **Bounded model choice:** The backend filters and sorts candidates first, then sends at most 12. The model selects up to three using the explicit preference and recent masked user messages. This adds cost and latency, and may miss a better option outside the shortlist. Rules could rank these options too; this implementation uses the model to consider conversation context and meet the exercise requirement.
- **Recheck without automatic replacement:** Selected options are checked again. Stale ones are removed, so fewer than three may appear. If all are stale, the system reports no verified alternatives rather than automatically ranking another set. No candidates means no model call.
- **No reservation hold:** Displayed alternatives are not locked. A second user can still book first. Confirmation checks the database again; another conflict asks for a preference again rather than automatically booking something else.

## Current scope and limitations

**Implemented:** form and chat booking, viewing, editing, and cancellation; room-linked equipment; owner checks; database overlap prevention; masking and model audit logs; and preference-based conflict suggestions, including conflicts at chat confirmation. Both servers start with `npm run dev`.

The remaining limits are:

- **Scheduling:** one room and date per booking, using one-hour slots within 08:00–18:00 Bangkok time. Holidays, recurring bookings, and per-room schedules are not implemented; `availability_rules` is reserved for future use.
- **Equipment:** at most one projector, camera, and microphone per room booking. Separate equipment bookings, custom quantities, and shorter equipment-only periods are not supported.
- **Changes and lifecycle:** owners can change dates, slots, and equipment before the first slot starts. Moving to another room requires a new booking and a separate cancellation, not an atomic room swap. Group size is checked at creation but is not stored or editable. Bookings are confirmed on creation; automatic transition to `completed` is not implemented.
- **Suggestion coverage:** automatic conflict suggestions apply to new chat bookings. The normal form refreshes availability after a conflict. Conflicting edits preserve the old reservation and require the user to adjust it manually. There is no waitlist or automatic rebooking.
- **Chat memory:** history is page-local, not saved across reloads or shared between devices. Requests use recent messages rather than the full conversation. Audit logs are not used to restore sessions. Chat handles one booking per confirmation.
- **Catalog:** room images are bundled with the frontend. Uploads and external image storage are not implemented.
- **Verification coverage:** 21 pytest API/database scenarios and 4 Cypress UI scenarios are implemented. Model responses are mocked for API tests, and application API responses are stubbed for UI tests. These checks do not measure real model quality, Neon networking, production load, or all browser layouts. Conflict suggestions are the chosen additional feature; MCP, an evaluation harness, and Laya are not implemented.
