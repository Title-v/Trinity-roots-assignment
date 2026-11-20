"""Test infrastructure only: isolated PostgreSQL, real API routes, mocked model HTTP."""


import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

os.environ["DATABASE_URL"] = "postgresql://test:test@127.0.0.1:1/trinity_test"
os.environ["DATABASE_URL_UNPOOLED"] = os.environ["DATABASE_URL"]
os.environ["OPENAI_API_KEY"] = ""
os.environ["OPENAI_MODEL"] = "test-model"
os.environ["SESSION_SECRET"] = "automated-test-session-secret-not-for-deployment"

import httpx2 as httpx
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from openai import DefaultHttpxClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

import assistant
import assistant_privacy
import database
from auth import password_hash
from availability import BOOKING_TIMEZONE
from main import app
from models import Resource, User

PASSWORD = "TestPassword123!"
BACKEND = Path(__file__).resolve().parents[2] / "backend"


@pytest.fixture(autouse=True)
def isolate_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(assistant_privacy, "AUDIT_PATH", tmp_path / "audit.jsonl")
    assistant.request_times.clear()
    monkeypatch.setattr(assistant, "last_cleanup", 0.0)

    def forbid_external_http(*args, **kwargs):
        raise AssertionError(
            "Unexpected external HTTP. Configure the model_http fixture."
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbid_external_http)
    yield
    app.dependency_overrides.clear()
    assistant.request_times.clear()


def docker(*args, timeout=30):
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True, timeout=timeout
    ).stdout.strip()


@pytest.fixture(scope="session")
def postgres_url():
    """Never accept an application DATABASE_URL for test database setup or cleanup."""
    try:
        docker("info", "--format", "{{.ServerVersion}}", timeout=15)
    except (OSError, subprocess.SubprocessError):
        pytest.fail(
            "Start Docker before running API tests. No application database was used."
        )
    name = f"trinity-tests-{uuid4().hex[:12]}"
    password = uuid4().hex
    try:
        docker(
            "run",
            "--detach",
            "--rm",
            "--name",
            name,
            "--publish",
            "127.0.0.1::5432",
            "--env",
            "POSTGRES_USER=test",
            "--env",
            f"POSTGRES_PASSWORD={password}",
            "--env",
            "POSTGRES_DB=trinity_test",
            "postgres:17",
            timeout=180,
        )
        port = docker("port", name, "5432/tcp").rsplit(":", 1)[1]
        url = f"postgresql://test:{password}@127.0.0.1:{port}/trinity_test"
        deadline = time.monotonic() + 45
        while True:
            try:
                with psycopg.connect(url, connect_timeout=1):
                    break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    pytest.fail(
                        "The disposable PostgreSQL instance did not become ready."
                    )
                time.sleep(0.2)
        with pytest.MonkeyPatch.context() as env:
            env.setenv("DATABASE_URL_UNPOOLED", url)
            command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
        yield url
    finally:
        # The random name belongs only to this run, even if startup failed before returning an ID.
        subprocess.run(
            ["docker", "rm", "--force", "--volumes", name],
            check=False,
            capture_output=True,
            timeout=30,
        )


@pytest.fixture
def db(postgres_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    database.get_engine.cache_clear()
    engine = database.get_engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE booking_equipment, bookings, availability_rules, resources, users RESTART IDENTITY CASCADE"
            )
        )
    with Session(engine) as session, session.begin():
        hashed = password_hash.hash(PASSWORD)
        session.add_all(
            [
                User(email=email, password_hash=hashed)
                for email in ["owner@example.com", "other@example.com"]
            ]
        )
        session.add_all(
            [
                Resource(
                    name="Oak Room",
                    kind="room",
                    capacity=10,
                    image_key="rooms/oak.webp",
                ),
                Resource(
                    name="Fern Room",
                    kind="room",
                    capacity=8,
                    image_key="rooms/fern.webp",
                ),
                Resource(
                    name="Lotus Room",
                    kind="room",
                    capacity=6,
                    image_key="rooms/lotus.webp",
                ),
                Resource(name="Projector 01", kind="equipment"),
                Resource(name="Camera 01", kind="equipment"),
                Resource(name="Microphone 01", kind="equipment"),
            ]
        )
    yield engine
    engine.dispose()
    database.get_engine.cache_clear()


@pytest.fixture
def clients(db):
    opened = []

    def make(email=None):
        client = TestClient(app)
        opened.append(client)
        if email:
            result = client.post(
                "/auth/login", json={"email": email, "password": PASSWORD}
            )
            assert result.status_code == 200, result.text
        return client

    yield make
    for client in opened:
        client.close()


@pytest.fixture
def owner(clients):
    return clients("owner@example.com")


@pytest.fixture
def other(clients):
    return clients("other@example.com")


@pytest.fixture
def catalog(db):
    with Session(db) as session:
        return {item.name: item.id for item in session.scalars(select(Resource))}


@pytest.fixture
def windows():
    from datetime import datetime, timedelta

    day = datetime.now(BOOKING_TIMEZONE).date() + timedelta(days=2)

    def make(hours=(14, 15), offset=0):
        date = day + timedelta(days=offset)
        return [
            {
                "starts_at": f"{date}T{h:02d}:00:00+07:00",
                "ends_at": f"{date}T{h + 1:02d}:00:00+07:00",
            }
            for h in hours
        ]

    return make


@pytest.fixture
def payload(catalog, windows):
    return {
        "resource_id": catalog["Oak Room"],
        "party_size": 5,
        "slots": windows(),
        "equipment": [],
    }


@pytest.fixture
def reserve():
    def create(client, body):
        response = client.post("/bookings/batch", json=body)
        assert response.status_code == 201, response.text
        assert len(response.json()["ids"]) == 1
        return response.json()["ids"][0]

    return create


@pytest.fixture
def proposal_args(payload):
    return {
        "day": payload["slots"][0]["starts_at"][:10],
        "people": 5,
        "start_hour": 14,
        "end_hour": 16,
        "room_name": "Oak Room",
        "prefer_largest": False,
        "equipment": [],
    }


@pytest.fixture
def model_http(monkeypatch):
    """Keep SDK parsing and real audit hooks. Only the model's HTTP transport is replaced."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    queued, calls, requests, responses = [], [], [], []

    def reply(tool, arguments):
        queued.append((tool, arguments))

    def handle(request):
        requests.append(request.content.decode())
        body = json.loads(request.content)
        calls.append(body)
        assert queued, "Unexpected model call"
        response = queued.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, int):
            result = httpx.Response(
                response,
                json={
                    "error": {
                        "message": "Simulated provider failure",
                        "type": "test_error",
                    }
                },
                request=request,
            )
        else:
            tool, arguments = response
            if callable(arguments):
                arguments = arguments(body)
            result = httpx.Response(
                200,
                json={
                    "id": "resp_test",
                    "object": "response",
                    "created_at": 1,
                    "status": "completed",
                    "model": "test-model",
                    "output": [
                        {
                            "type": "function_call",
                            "id": "fc_test",
                            "call_id": "call_test",
                            "name": tool,
                            "arguments": json.dumps(arguments),
                        }
                    ],
                },
                request=request,
            )
        responses.append(result.text)
        return result

    def http_client():
        with assistant_privacy.audited_http_client() as template:
            hooks = template.event_hooks
        return DefaultHttpxClient(
            transport=httpx.MockTransport(handle),
            event_hooks=hooks,
            follow_redirects=False,
        )

    monkeypatch.setattr(assistant, "audited_http_client", http_client)
    return SimpleNamespace(
        reply=reply, queued=queued, calls=calls, requests=requests, responses=responses
    )
