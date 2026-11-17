import json
import os
import stat
from datetime import UTC, datetime
from uuid import uuid4

from httpx import Request, Response
from openai import DefaultHttpxClient
from presidio_analyzer import Pattern, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from database import PROJECT_ROOT

PATTERNS = {
    "THAI_ID": r"(?<!\d)\d(?:[ -]?\d){12}(?![ -]?\d)",
    "PHONE": (
        r"(?<![\d+])(?:0[689]\d|\+66[ -]?[689]\d)(?:[ .-]?\d){7}(?!\d)"
        r"|(?<![\d+])(?:0[2-57]|\+66[ -]?[2-57])(?:[ .-]?\d){7}(?!\d)"
    ),
    "EMAIL": r"(?<![\w.+-])[\w.!#$%&'*+/=?^_`{|}~-]+@[\w-]+(?:\.[\w-]+)+",
    "API_KEY": (
        r"\b(?:sk-(?:proj-|svcacct-|ant-)?[A-Za-z0-9_-]{12,}"
        r"|AIza[A-Za-z0-9_-]{35}|gh[pousr]_[A-Za-z0-9]{20,}"
        r"|github_pat_[A-Za-z0-9_]{20,}|(?:AKIA|ASIA)[A-Z0-9]{16})\b"
        r"|\b(?:[A-Za-z0-9_]*api[_ -]?key|access[_ -]?token|secret[_ -]?key)"
        r"""["']?\s*[:=]\s*["']?[A-Za-z0-9_./+=-]{8,}"""
        r"|\bBearer[ \t]+[A-Za-z0-9_./+=-]{12,}"
    ),
}
recognizers = [
    PatternRecognizer(entity, patterns=[Pattern(entity, regex, 0.85)])
    for entity, regex in PATTERNS.items()
]
anonymizer = AnonymizerEngine()


# Replace recognized personal data and secret patterns before text reaches the model.
def mask_sensitive(text: str) -> str:
    matches = [
        match
        for recognizer in recognizers
        for match in recognizer.analyze(text, recognizer.supported_entities)
    ]
    return anonymizer.anonymize(
        text,
        matches,
        operators={"DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"})},
    ).text


AUDIT_PATH = PROJECT_ROOT / ".assistant-audit.jsonl"


# Append the exact model payload to a private JSONL file with a request correlation ID.
def audit_event(request_id: str, event: str, body: str, **metadata: int) -> None:
    line = json.dumps(
        {
            "time": datetime.now(UTC).isoformat(),
            "request_id": request_id,
            "event": event,
            "body": body,
            **metadata,
        },
        ensure_ascii=False,
    )
    fd = os.open(
        AUDIT_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(fd, "a", encoding="utf-8") as log:
        mode = os.fstat(log.fileno())
        if not stat.S_ISREG(mode.st_mode) or mode.st_mode & 0o077:
            raise PermissionError("Assistant audit log must be a private regular file")
        log.write(line + "\n")


# Log outbound request bodies and inbound response bodies, excluding HTTP headers.
def audited_http_client() -> DefaultHttpxClient:
    request_id = uuid4().hex

    def log_request(request: Request) -> None:
        audit_event(request_id, "request", request.read().decode("utf-8"))

    def log_response(response: Response) -> None:
        audit_event(
            request_id,
            "response",
            response.read().decode("utf-8", errors="replace"),
            status=response.status_code,
        )

    return DefaultHttpxClient(
        follow_redirects=False,
        event_hooks={"request": [log_request], "response": [log_response]},
    )
