# Data model and booking flows

[Back to README](../README.md)

These Mermaid diagrams render directly on GitHub. API paths below are FastAPI routes; the React app calls them through Vite's `/api` proxy. Protected requests use the signed session cookie. Database reads and writes are grouped for readability.

## ER diagram

```mermaid
erDiagram
    users ||..o{ bookings : owns
    resources ||..o{ bookings : reserves_room
    bookings ||..o{ booking_equipment : includes
    resources ||..o{ booking_equipment : assigns_unit
    resources ||..o{ availability_rules : has_schedule

    users {
        int id PK
        varchar email UK
        varchar password_hash
    }
    resources {
        int id PK
        varchar name
        varchar kind "room or equipment"
        int capacity "nullable"
        varchar image_key "nullable"
        boolean is_active
    }
    bookings {
        int id PK
        int user_id FK
        int resource_id FK "room"
        timestamptz starts_at
        timestamptz ends_at
        tstzmultirange time_ranges
        varchar status
        int version
        timestamptz created_at
    }
    booking_equipment {
        int id PK
        int booking_id FK
        int resource_id FK "physical equipment unit"
        tstzmultirange time_ranges
        varchar status
    }
    assistant_audit_logs {
        int id PK
        varchar request_id "correlation ID"
        varchar event "request or response"
        text body "exact model payload"
        int status "nullable response status"
        timestamptz created_at
    }
    availability_rules {
        int id PK
        int resource_id FK
        int weekday "0 Monday to 6 Sunday"
        time opens_at
        time closes_at
    }
```

`assistant_audit_logs` is an independent private log table, correlated by `request_id` rather than a booking foreign key. It is used on Vercel; local development defaults to the JSONL file.

A user can own many bookings. Each booking reserves one room and can include multiple equipment units through `booking_equipment`. Both rooms and individual equipment units live in `resources`; the backend enforces their roles. Each child row belongs to exactly one referenced parent. The dotted relationships are non-identifying: child tables have their own primary keys.

`time_ranges` stores the actual occupied periods, including gaps. `starts_at` and `ends_at` store the outer boundaries. Group size is validated against capacity when creating a booking but is not stored as a booking column. The schema supports `confirmed`, `cancelled`, and `completed`; automatic completion is not implemented. `availability_rules` is reserved for future schedules; current opening hours come from `backend/availability.py`.

The unique pair `(booking_id, resource_id)` prevents duplicate equipment links. PostgreSQL exclusion constraints prevent overlapping confirmed reservations for the same room or equipment unit. These constraints are explained in [How bookings stay consistent](design.md#how-bookings-stay-consistent).

## Normal booking through the form

This diagram shows a successful booking. Browsing rooms does not require sign-in, but confirmation does. Equipment is optional, and no model call is needed. If a room or equipment conflict occurs during the transaction, the backend rolls back all changes and returns 409. The normal form shows the error and refreshes availability so the user can change the selection.

```mermaid
sequenceDiagram
    actor User
    participant React
    participant FastAPI
    participant PostgreSQL

    User->>React: Open booking page
    React->>FastAPI: GET /rooms
    FastAPI->>PostgreSQL: Read active room catalog
    PostgreSQL-->>FastAPI: Rooms, capacities and image references
    FastAPI-->>React: Room catalog
    User->>React: Submit date and group size
    React->>FastAPI: GET /rooms/slots with day and people
    FastAPI->>PostgreSQL: Read rooms and confirmed booking ranges
    PostgreSQL-->>FastAPI: Current reservations
    FastAPI-->>React: Available, booked and past hourly slots
    Note over React,FastAPI: Availability refreshes about every five seconds
    User->>React: Select a room and hourly slots
    React->>FastAPI: POST /equipment/availability with slots
    FastAPI->>PostgreSQL: Find equipment free for all selected slots
    PostgreSQL-->>FastAPI: Available units
    FastAPI-->>React: Available counts by equipment type
    User->>React: Choose optional equipment and confirm after signing in
    React->>FastAPI: POST /bookings/batch with session cookie
    FastAPI->>FastAPI: Authenticate and validate hourly slots
    FastAPI->>PostgreSQL: Begin transaction and read selected room
    PostgreSQL-->>FastAPI: Room type, active status and capacity
    FastAPI->>FastAPI: Validate room and group size
    FastAPI->>PostgreSQL: Insert confirmed room booking with selected ranges
    opt Equipment requested
        FastAPI->>PostgreSQL: Lock inventory and read available units
        PostgreSQL-->>FastAPI: Units free for the entire booking
        FastAPI->>FastAPI: Choose one unit per requested category
        FastAPI->>PostgreSQL: Insert equipment reservations with the same ranges
    end
    Note over FastAPI,PostgreSQL: Constraints reject overlapping confirmed room or equipment ranges
    FastAPI->>PostgreSQL: Commit the complete transaction
    PostgreSQL-->>FastAPI: Commit succeeds
    FastAPI-->>React: 201 Created with booking ID
    React-->>User: Show confirmation
    React->>FastAPI: Refresh room availability
```

## Booking through the AI assistant

Chat requires sign-in. The model returns a tool call, and FastAPI validates its arguments before running the corresponding Python function. A clarification waits for another user message. A complete request either produces room proposals or asks about alternative preferences. Only a selected proposal with explicit confirmation reaches the booking API.

```mermaid
sequenceDiagram
    actor User
    participant React
    participant FastAPI
    participant OpenAI
    participant PostgreSQL

    loop Each chat turn
        User->>React: Enter request or answer a clarification
        React->>FastAPI: POST /assistant/chat with recent messages
        FastAPI->>FastAPI: Authenticate, check rate limit and mask sensitive text
        FastAPI->>OpenAI: Send masked context and allowed tool schemas
        OpenAI-->>FastAPI: Return tool name and structured arguments
        Note over FastAPI,OpenAI: Audit logs capture exact model request and response bodies
        FastAPI->>FastAPI: Validate arguments and dispatch the selected tool
        alt Booking details are missing
            FastAPI-->>React: Return a fixed clarification
            React-->>User: Ask for the missing date, people, times or equipment preference
        else Booking details are complete
            FastAPI->>PostgreSQL: Read room availability and requested equipment stock
            PostgreSQL-->>FastAPI: Current room and equipment data
            FastAPI->>FastAPI: Check the complete requested period
            alt Matching rooms are available
                FastAPI-->>React: Return room proposals without reserving them
                React-->>User: Show photos, capacities, slots and equipment
            else No matching room or required equipment
                FastAPI-->>React: Return a preference question and original booking details
                React-->>User: Ask same time, same room, or either
                Note over React,FastAPI: Use the alternatives flow shown in the next diagram
            end
        end
    end
    opt A proposal is available and the user chooses to confirm
        User->>React: Select a room and confirm the reviewed details
        React->>FastAPI: POST /bookings/batch with selected proposal
        FastAPI->>FastAPI: Authenticate and validate booking rules again
        Note over FastAPI,PostgreSQL: Use the same atomic room and equipment transaction as the form
        FastAPI->>PostgreSQL: Attempt room and equipment reservation
        alt Room and equipment can be saved
            FastAPI->>PostgreSQL: Commit transaction
            PostgreSQL-->>FastAPI: Commit succeeds
            FastAPI-->>React: 201 Created with booking ID
            React-->>User: Show booking confirmation
        else Room overlap or equipment unavailable
            FastAPI->>PostgreSQL: Roll back transaction
            FastAPI-->>React: 409 Conflict
            React-->>User: Ask same time, same room, or either before finding alternatives
        end
    end
```

The booking transaction is expanded in the normal-form diagram. Room overlaps are rejected by PostgreSQL. Equipment shortages can also be detected by the backend after reading available units. Both produce a rollback and 409, rather than leaving a partial booking. Model failures or invalid model arguments stop the proposal flow with an error. They do not create a reservation, and the normal form remains available.

## Someone else books before confirmation

This example starts with User A reviewing a proposal. User B confirms an overlapping room booking first. User B's UI is omitted to keep the diagram readable. The database rejects User A's reservation, and React asks for a preference before calling the alternatives endpoint. No model call is needed just to show that question.

```mermaid
sequenceDiagram
    actor UserA as User A
    participant React
    actor UserB as User B
    participant FastAPI
    participant OpenAI
    participant PostgreSQL

    Note over UserA,React: User A is reviewing an available room proposal
    UserB->>FastAPI: POST /bookings/batch for the same room and time
    FastAPI->>FastAPI: Authenticate User B and validate booking rules
    FastAPI->>PostgreSQL: Save and commit User B booking
    PostgreSQL-->>FastAPI: Commit succeeds
    FastAPI-->>UserB: 201 Created
    UserA->>React: Confirm the earlier proposal
    React->>FastAPI: POST /bookings/batch
    FastAPI->>FastAPI: Authenticate and validate booking rules
    FastAPI->>PostgreSQL: Begin transaction and attempt overlapping room insert
    PostgreSQL-->>FastAPI: Exclusion violation, SQLSTATE 23P01
    FastAPI->>PostgreSQL: Roll back User A transaction
    FastAPI-->>React: 409 Conflict
    React-->>UserA: Booking failed - same time, same room, or either?
    UserA->>React: Choose a preference
    React->>FastAPI: POST /assistant/alternatives with failed details and preference
    FastAPI->>FastAPI: Authenticate, check rate limit and validate input
    FastAPI->>PostgreSQL: Read room and equipment availability
    PostgreSQL-->>FastAPI: Current availability
    FastAPI->>FastAPI: Apply preference and build up to 12 valid candidates
    alt Candidates exist
        FastAPI->>OpenAI: Send masked context, preference and candidate details
        OpenAI-->>FastAPI: Select up to 3 known candidate IDs
        FastAPI->>FastAPI: Validate IDs and remove duplicates
        FastAPI->>PostgreSQL: Reload availability for selected candidates
        PostgreSQL-->>FastAPI: Latest room and equipment data
        FastAPI->>FastAPI: Recheck preference and rules, drop stale candidates
        FastAPI-->>React: Return verified alternatives or an empty result
    else No candidates match the preference
        FastAPI-->>React: No verified alternatives, without calling the model
    end
    alt Verified alternatives are available
        React-->>UserA: Show checked room and time options
        opt User chooses to confirm an alternative
            UserA->>React: Select an option and confirm again
            React->>FastAPI: POST /bookings/batch
            FastAPI->>FastAPI: Authenticate and validate booking rules again
            FastAPI->>PostgreSQL: Attempt atomic booking under the same constraints
            alt Reservation succeeds
                FastAPI->>PostgreSQL: Commit transaction
                PostgreSQL-->>FastAPI: Commit succeeds
                FastAPI-->>React: 201 Created with booking ID
                React-->>UserA: Show booking confirmation
            else Another room or equipment conflict
                FastAPI->>PostgreSQL: Roll back transaction
                FastAPI-->>React: 409 Conflict
                React-->>UserA: Ask for a preference again
            end
        end
    else No verified alternatives remain
        React-->>UserA: Choose another preference or start a new search
    end
```

Selected alternatives still require a separate user confirmation. The final availability check does not hold a room or equipment unit. If the model call fails or returns invalid IDs, the endpoint returns an error instead of showing unverified options. The UI offers a retry, and the normal booking form remains available. If options are shown but the user does not confirm, no booking is written.
