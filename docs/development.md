# Development and testing

[Back to README](../README.md)

## Check the app

After installing the project dependencies, start Docker and run both test suites from the project root:

```sh
npm test
```

The suite runs **21 pytest API/database cases and 4 Cypress UI cases**. It needs no LLM key, Neon credentials, or running app servers. See the [test cases and expected results](../tests/README.md) for the split between API and UI assertions.

- **API tests:** create a disposable PostgreSQL container, apply real Alembic migrations, and clean up the container afterward. The first run downloads `postgres:17`. Tests override application database settings, use separate test accounts, and keep model audit logs in temporary files. Real model HTTP requests are blocked and replaced with controlled responses.
- **UI tests:** start a separate Vite server on a free local port with no backend proxy, then run Cypress in its bundled headless Electron browser. Application API responses are stubbed, and unexpected API calls fail the test. The server stops when the run finishes. No database is needed for this suite.

Run either suite separately:

```sh
npm run test:api
npm run test:ui
```

Cypress and its TypeScript test compiler are installed with the root dev dependencies. Its first installation downloads the browser runner. Failed UI tests save screenshots under `tests/ui/screenshots/`, which Git ignores. The tests check browser interactions, not visual snapshots or mobile layouts. Pytest mocks the model, so it does not prove real language understanding or complete prompt-injection resistance.

Build and lint separately:

```sh
npm run build
npm --prefix frontend run lint
npm run lint:tests
uv run --directory backend ruff check . ../tests/api
```

With `npm run dev` running, check the database connection through the frontend proxy:

```sh
curl -fsS http://127.0.0.1:5173/api/health/db
```

A successful response is `{"status":"ok","database":"connected"}`. This checks connectivity, not the full booking workflow.

## Project structure

All automated test files are grouped at the project root:

```text
tests/
  README.md
  pytest.ini
  api/
    conftest.py
    test_*.py
  ui/
    cypress.config.mjs
    eslint.config.mjs
    tsconfig.json
    run.mjs
    e2e/
      booking.cy.ts
requirements.txt
```

| Location | Purpose |
| --- | --- |
| `frontend/src/` | React pages, booking forms, and the assistant panel |
| `docs/` | Setup, user guide, design, development notes, and diagrams |
| `tests/README.md` | API/UI test cases and expected results |
| `tests/api/` | Pytest API tests, disposable PostgreSQL fixtures, and mocked model HTTP |
| `tests/ui/` | Cypress specs, configuration, and isolated UI test runner |
| `tests/pytest.ini` | API test discovery and backend import path |
| `requirements.txt` | Locked Python runtime and development dependencies exported from uv |
| `backend/bookings.py` | Availability, creation, rescheduling, and cancellation |
| `backend/assistant.py` | Model calls, tools, and chat rate limits |
| `backend/booking_alternatives.py` | Build alternative bookings, ask the model to select them, and recheck availability |
| `backend/assistant_privacy.py` | Masking and request/response logs |
| `backend/auth.py` | Registration, login, and account checks |
| `backend/models.py` and `backend/migrations/` | Database models and schema history |
| `neon.ts` | Neon branch configuration |

The application tables are `users`, `resources`, `bookings`, `booking_equipment`, and `availability_rules`. Room capacity and individual equipment units are stored in `resources`. `booking_equipment` links assigned units to a room booking and records their reserved periods. Opening hours currently come from `backend/availability.py`. The `availability_rules` table is reserved for future schedules per resource.

The time-range migration backfills existing bookings with their original periods. Earlier bookings keep their individual IDs. New selections are saved together as one booking.
