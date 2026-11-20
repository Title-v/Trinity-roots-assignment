"""ALT-01, ALT-02 and ALT-04. ALT-03's UI transitions are tested by Cypress UI-02."""

import json
from datetime import datetime


def select_candidates(payload):
    candidates = json.loads(payload["input"][0]["content"])["candidates"]
    assert 1 <= len(candidates) <= 12
    return {"candidate_ids": [item["candidate_id"] for item in candidates[:3]]}


def test_alt_01_preferences_preserve_booking_constraints(
    owner, other, payload, windows, proposal_args, model_http, reserve
):
    reserve(other, payload)
    model_http.reply("propose_room_booking", proposal_args)
    result = owner.post(
        "/assistant/chat",
        json={"messages": [{"role": "user", "content": "Book Oak Room"}]},
    )
    assert result.status_code == 200
    assert result.json()["alternative_request"]["preference"] is None
    assert result.json()["proposals"] == [] and len(model_http.calls) == 1
    for preference in ["same_time", "same_room", "flexible"]:
        periods = windows([12, 14]) if preference == "same_room" else payload["slots"]
        request = {
            **payload,
            "slots": periods,
            "room_name": "Oak Room",
            "equipment": ["Projector"],
            "preference": preference,
        }
        model_http.reply("suggest_booking_alternatives", select_candidates)
        response = owner.post("/assistant/alternatives", json=request)
        assert response.status_code == 200, response.text
        proposals = response.json()["proposals"]
        assert 1 <= len(proposals) <= 3
        for option in proposals:
            assert option["party_size"] == 5 and option["equipment"] == ["Projector"]
            assert len(option["slots"]) == len(periods)
            if preference == "same_time":
                assert (
                    option["resource_id"] != payload["resource_id"]
                    and option["slots"] == periods
                )
            if preference == "same_room":
                assert (
                    option["resource_id"] == payload["resource_id"]
                    and option["slots"] != periods
                )
            # A shared shift preserves duration and gaps, not just the outer start/end.
            shifts = set()
            for old, new in zip(periods, option["slots"], strict=True):
                assert old["starts_at"][:10] == new["starts_at"][:10]
                for key in ["starts_at", "ends_at"]:
                    shifts.add(
                        datetime.fromisoformat(new[key])
                        - datetime.fromisoformat(old[key])
                    )
            assert len(shifts) == 1
    assert owner.get("/bookings").json() == []


def test_alt_02_same_time_with_no_matches_does_not_relax_preference(
    owner, other, payload, catalog, model_http, reserve
):
    for name in ["Oak Room", "Fern Room", "Lotus Room"]:
        reserve(other, {**payload, "resource_id": catalog[name]})
    response = owner.post(
        "/assistant/alternatives",
        json={**payload, "room_name": "Oak Room", "preference": "same_time"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["proposals"] == [] and result["proposal"] is None
    assert result["alternative_request"]["preference"] is None
    for key in ["resource_id", "party_size", "slots", "equipment"]:
        assert result["alternative_request"][key] == payload[key]
    assert model_http.calls == [] and owner.get("/bookings").json() == []


def test_alt_04_candidate_taken_during_model_call_is_not_returned(
    owner, other, payload, catalog, model_http, reserve
):
    reserve(other, payload)

    def book_before_reply(request):
        candidate = json.loads(request["input"][0]["content"])["candidates"][0]
        reserve(other, {**payload, "resource_id": catalog[candidate["room_name"]]})
        return {"candidate_ids": [candidate["candidate_id"]]}

    model_http.reply("suggest_booking_alternatives", book_before_reply)
    response = owner.post(
        "/assistant/alternatives", json={**payload, "preference": "same_time"}
    )
    assert response.status_code == 200
    result = response.json()
    assert (
        result["proposals"] == []
        and result["alternative_request"]["preference"] is None
    )
    assert result["alternative_request"]["slots"] == payload["slots"]
    assert "latest availability check" in result["reply"]
    assert "No other room" not in result["reply"]
    assert len(model_http.calls) == 1 and owner.get("/bookings").json() == []
