# Test cases

Implemented: **21 pytest cases and 4 Cypress cases**. Each case ID below maps to one named test. Run both suites with `npm test` from the project root. See [test tool installation](../docs/development.md#install-test-tools) before the first run, or [open Cypress](../docs/development.md#watch-ui-tests-in-cypress) to watch the UI automation.

| Framework | Responsibility | Test boundary |
| --- | --- | --- |
| **pytest** | API responses, authentication, database state, transactions, model contracts and logs | Use FastAPI TestClient, real isolated PostgreSQL for database cases, and mocked model responses. No browser assertions. |
| **Cypress** | User input, rendered messages, button states, navigation and requests sent by React | Stub application API responses with `cy.intercept()` to make UI states predictable. Do not repeat database or model-validation assertions. |

## pytest — API and database: 21 scenarios

### Accounts and ownership — 2 scenarios

Implementation: [test_access.py](api/test_access.py).

| Case | Input or action | Expected result and reason |
| --- | --- | --- |
| ACCESS-01 | Call the registration, login, protected booking and logout APIs, then retry the protected request | Registration and login succeed. The cleared session receives 401, so a booking cannot be made without an authenticated owner. |
| ACCESS-02 | Account B lists bookings and tries to edit or cancel account A's reservation | B cannot see A's booking in its list or change it. A's reservation remains unchanged. This directly checks the ownership requirement. |

### Booking and equipment consistency — 10 scenarios

Implementation: [test_bookings.py](api/test_bookings.py).

| Case | Input or action | Expected result and reason |
| --- | --- | --- |
| BOOK-01 | Create one room booking with equipment for 08:00–09:00 and 10:00–11:00, then view it | Return one booking containing both slots and equipment. The gap 09:00–10:00 remains bookable, including its touching boundaries. This checks creation, viewing, and actual occupied ranges. |
| BOOK-02 | Request a slot before 08:00, after 18:00, or starting at a half-hour | Reject with 422 and write nothing. These representative inputs check opening hours and the one-hour slot rule. |
| BOOK-03 | Request a past slot | Reject with 422 and write nothing. Opening hours alone must not permit historical bookings. |
| BOOK-04 | Request more people than the room capacity | Reject with 422 and write nothing. A caller must not bypass the frontend capacity filter. |
| BOOK-05 | Two accounts submit overlapping slots for the same room simultaneously | Exactly one 201 and one 409, with only one booking saved. This is the central conflict-prevention requirement. |
| BOOK-06 | Two accounts book different rooms while requesting the last available projector for the same period | Only one transaction succeeds. The losing request saves neither a room booking nor equipment. This checks inventory locking and atomic rollback. |
| BOOK-07 | Edit a booking from 08:00–10:00 to 08:00–09:00 plus 10:00–11:00 | Keep the same booking ID and move its equipment with it. Release 09:00–10:00 for another user. This checks that edits do not leave stale reservations. |
| BOOK-08 | Edit an existing reservation into a room conflict or equipment shortage | Return 409 and retain the original slots and equipment. Check both causes because they fail at different points in the transaction. |
| BOOK-09 | Cancel a booking with equipment, then attempt to edit it | Mark the room and equipment cancelled, make their slots bookable again, and reject the edit. This checks cancellation and lifecycle rules. |
| BOOK-10 | Call the edit or cancellation API for a booking that has started | Return 409 and preserve the reservation. The backend must enforce lifecycle rules independently of the interface. |

### AI proposals and failure handling — 3 scenarios

Implementation: [test_assistant.py](api/test_assistant.py).

| Case | Input or action | Expected result and reason |
| --- | --- | --- |
| AI-01 | Send chat API requests with mocked tool calls that first omit an end time or equipment preference, then supply complete details | Return a clarification for missing details. A complete request returns proposals without database writes. A separate authenticated POST /bookings/batch creates the booking. |
| AI-02 | Call the chat API without an LLM key, or simulate a model timeout/provider error, then call the booking API | The chat API returns 503 with an error detail and creates no booking. POST /bookings/batch still succeeds. This proves the normal form's API remains available, not that its rendered UI works. |
| AI-03 | The mocked model supplies invalid booking arguments or an unknown alternative candidate ID | Return 503 without actionable proposals or database changes. Model output is not trusted just because it uses a tool. |

### Guardrails and request limits — 3 scenarios

Implementation: [test_guardrails.py](api/test_guardrails.py).

| Case | Input or action | Expected result and reason |
| --- | --- | --- |
| GUARD-01 | Send a room request containing a synthetic Thai ID, phone, email and API key, including an ID followed by a phone with one separating space | Mask all four values before the model request while retaining the date, time and group size. The adjacent-number input prevents regression of the corrected masking boundary. |
| GUARD-02 | Capture one mocked model request and response | Log the exact masked request and received response with matching request IDs in a private 0600 file, and verify the database sink used on Vercel. Exclude headers and pre-mask text. This checks the exercise's audit-log requirement. |
| GUARD-03 | Account A reaches its shared chat/alternatives quota while account B sends a request; then advance the clock | Limit A with 429 and Retry-After, allow B, and allow A again after expiry. This checks account isolation and the rolling time window. |

### Conflict suggestions — 3 scenarios

Implementation: [test_alternatives.py](api/test_alternatives.py).

| Case | Input or action | Expected result and reason |
| --- | --- | --- |
| ALT-01 | Request a taken room through the chat API, then submit same_time, same_room, or flexible to the alternatives API | First return a preference question and the original details. After a preference is supplied, returned proposals respect that constraint and preserve the date, group size, equipment, duration and gaps. |
| ALT-02 | All rooms are full at 14:00–16:00, but other times are free; call the alternatives API with same_time | Return an empty proposals list and alternative_request with the original details and preference reset to null. Do not offer other times, call the model, or write a booking. |
| ALT-04 | Book a selected candidate during the mocked model call, before the alternatives API returns | Recheck PostgreSQL and omit that candidate from the API response. If none remain, return the preference question and retained details without claiming every possible room is full. |

## Cypress — UI: 4 scenarios

Implementation: [booking.cy.ts](ui/e2e/booking.cy.ts).

These cases inspect React behavior using controlled API responses. They do not claim that the backend has saved data or that the real LLM failed. Those checks belong to pytest. Real overlap prevention belongs to BOOK-05; UI-02 checks the client reaction to a supplied 409.

| Case | User action and API setup | Expected UI result | Covered by pytest separately |
| --- | --- | --- | --- |
| **UI-01** | Fill date and group size, choose a room, hourly slots and equipment, and press Confirm. Stub catalog, availability, creation and My bookings responses | React sends the chosen room, slots, group size and equipment in the booking request. Show confirmation only after the successful response. Opening My bookings renders the returned room, date, slots and equipment correctly. | BOOK-01 checks that the API actually stores and returns the correct reservation. Cypress checks form-to-request mapping and displayed data only. |
| **UI-02** | Return an AI room proposal, select it, then return 409 when Confirm is pressed. Choose an alternative preference | No booking request is sent before explicit confirmation. Confirm is disabled until a room is selected. After 409, remove stale choices and show preference buttons. Do not request alternatives until the user chooses a preference. The outgoing request retains the original details. | BOOK-05 proves real simultaneous requests cannot double-book. ALT-01 checks the alternatives API contract. Cypress checks the frontend transition after a supplied 409. |
| **UI-03** | Choose Same time and return an empty proposals list with the original alternative_request. Then explicitly choose Same room and return a later-time proposal | Show the no-match reply and preference controls while retaining the original date, slots and equipment. Send no automatic follow-up request. Only the new explicit choice sends same_room. Display the returned proposal and require selection and confirmation again. | ALT-02 checks that the backend never generates other times for same_time. Cypress checks that React keeps the draft and waits for user input. |
| **UI-04** | Return 503 for the chat request, while form availability and booking endpoints return successful responses. Submit the normal booking form | Show the assistant error, restore the unsent message and end the loading state. The form remains interactive and can send a booking request and display its successful response. | AI-02 checks real backend handling of a missing key, model timeout or provider error. Cypress checks the UI response to a supplied 503, not the provider connection. |
