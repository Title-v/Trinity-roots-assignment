"""AI-01 through AI-03: backend contracts, not model language quality or UI behavior."""

import httpx2 as httpx

import assistant


def chat(client, message):
    return client.post(
        "/assistant/chat", json={"messages": [{"role": "user", "content": message}]}
    )


def test_ai_01_clarify_then_propose_without_writing(
    owner, proposal_args, model_http, reserve
):
    for field, reason in [("end_hour", "end_time"), ("equipment", "equipment_needed")]:
        model_http.reply("propose_room_booking", {**proposal_args, field: None})
        response = chat(owner, "Book Oak Room")
        assert response.status_code == 200
        assert response.json()["reply"] == assistant.CLARIFICATIONS[reason][1]
        assert response.json()["proposals"] == []
        assert owner.get("/bookings").json() == []
    model_http.reply("propose_room_booking", proposal_args)
    result = chat(owner, "Use those times, no equipment.").json()
    assert result["proposals"] and owner.get("/bookings").json() == []
    reserve(owner, result["proposals"][0])
    assert len(owner.get("/bookings").json()) == 1


def test_ai_02_model_failures_do_not_disable_booking_api(
    owner, payload, windows, model_http, monkeypatch, reserve
):
    for index, failure in enumerate(["no-key", "timeout", "provider-error"]):
        before = owner.get("/bookings").json()
        with monkeypatch.context() as env:
            if failure == "no-key":
                env.setenv("OPENAI_API_KEY", "")
            elif failure == "timeout":
                model_http.queued.append(httpx.ReadTimeout("Simulated model timeout"))
            else:
                model_http.queued.append(503)
            response = chat(owner, "Find a room")
        assert response.status_code == 503 and response.json()["detail"]
        assert owner.get("/bookings").json() == before
        reserve(owner, {**payload, "slots": windows([8 + index])})
    assert (
        len(model_http.calls) == 2
    )  # Missing configuration fails before an HTTP call.


def test_ai_03_invalid_model_arguments_and_unknown_candidate_are_rejected(
    owner, other, payload, proposal_args, model_http, reserve
):
    model_http.reply("propose_room_booking", {**proposal_args, "people": -1})
    result = chat(owner, "Book a room")
    assert result.status_code == 503 and "proposals" not in result.json()
    reserve(other, payload)
    model_http.reply("suggest_booking_alternatives", {"candidate_ids": ["invented_id"]})
    result = owner.post(
        "/assistant/alternatives", json={**payload, "preference": "same_time"}
    )
    assert result.status_code == 503 and "proposals" not in result.json()
    assert owner.get("/bookings").json() == []
    assert len(other.get("/bookings").json()) == 1
