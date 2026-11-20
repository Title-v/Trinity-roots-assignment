"""BOOK-01 through BOOK-10: rules and transactions on migrated PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from availability import BookingWindow
from bookings import set_booking_slots
from models import Booking, BookingEquipment


def counts(db):
    with Session(db) as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in [Booking, BookingEquipment]
        )


def slots(client, room_id, windows):
    response = client.get(
        f"/rooms/{room_id}/slots", params={"day": windows[0]["starts_at"][:10]}
    )
    assert response.status_code == 200
    return {
        datetime.fromisoformat(item["starts_at"]).hour: item["status"]
        for item in response.json()
    }


def test_book_01_multiple_slots_keep_gap_bookable(
    owner, other, payload, windows, reserve, db
):
    body = {**payload, "slots": windows([8, 10]), "equipment": ["Projector"]}
    booking_id = reserve(owner, body)
    result = owner.get("/bookings").json()
    assert len(result) == 1 and result[0]["id"] == booking_id
    assert (
        len(result[0]["slots"]) == 2
        and result[0]["equipment"][0]["category"] == "Projector"
    )
    available = slots(owner, body["resource_id"], body["slots"])
    assert [available[h] for h in [8, 9, 10]] == ["booked", "available", "booked"]
    reserve(other, {**body, "slots": windows([9])})
    assert counts(db) == (2, 2)


def test_book_02_invalid_business_hours_and_slot_boundary(owner, payload, windows, db):
    half_hour = [
        {
            key: value.replace(":00:00", ":30:00")
            for key, value in windows([14])[0].items()
        }
    ]
    for periods in [windows([7]), windows([18]), half_hour]:
        response = owner.post("/bookings/batch", json={**payload, "slots": periods})
        assert response.status_code == 422, response.text
    assert counts(db) == (0, 0)


def test_book_03_past_slot_rejected(owner, payload, windows, db):
    assert (
        owner.post(
            "/bookings/batch", json={**payload, "slots": windows([14], offset=-3)}
        ).status_code
        == 422
    )
    assert counts(db) == (0, 0)


def test_book_04_capacity_enforced_by_api(owner, payload, db):
    assert (
        owner.post("/bookings/batch", json={**payload, "party_size": 11}).status_code
        == 422
    )
    assert counts(db) == (0, 0)


def concurrent_creates(db, requests):
    # Synchronize independent transactions immediately before INSERT, not just before HTTP calls.
    barrier = Barrier(2)

    def before_insert(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO bookings "):
            barrier.wait(timeout=10)

    event.listen(db, "before_cursor_execute", before_insert)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(client.post, "/bookings/batch", json=body)
                for client, body in requests
            ]
            return [future.result(timeout=20).status_code for future in futures]
    finally:
        event.remove(db, "before_cursor_execute", before_insert)


def test_book_05_simultaneous_room_requests_have_one_winner(owner, other, payload, db):
    assert sorted(concurrent_creates(db, [(owner, payload), (other, payload)])) == [
        201,
        409,
    ]
    assert counts(db) == (1, 0)


def test_book_06_last_equipment_unit_is_not_double_allocated(
    owner, other, payload, catalog, db
):
    first = {**payload, "equipment": ["Projector"]}
    second = {**first, "resource_id": catalog["Fern Room"]}
    assert sorted(concurrent_creates(db, [(owner, first), (other, second)])) == [
        201,
        409,
    ]
    assert counts(db) == (1, 1)  # The losing room insert is rolled back as well.


def test_book_07_edit_releases_removed_room_and_equipment_slots(
    owner, other, payload, windows, reserve
):
    booking_id = reserve(
        owner, {**payload, "slots": windows([8, 9]), "equipment": ["Projector"]}
    )
    assert (
        owner.patch(
            f"/bookings/{booking_id}", json={"slots": windows([8, 10])}
        ).status_code
        == 204
    )
    result = owner.get("/bookings").json()[0]
    assert (
        result["id"] == booking_id and result["equipment"][0]["category"] == "Projector"
    )
    available = slots(owner, payload["resource_id"], windows([8]))
    assert [available[h] for h in [8, 9, 10]] == ["booked", "available", "booked"]
    reserve(other, {**payload, "slots": windows([9]), "equipment": ["Projector"]})


def test_book_08_conflicting_edit_preserves_original_state(
    owner, other, payload, windows, catalog, reserve, db
):
    booking_id = reserve(
        owner, {**payload, "slots": windows([8]), "equipment": ["Camera"]}
    )
    reserve(other, {**payload, "slots": windows([10])})
    reserve(
        other,
        {
            **payload,
            "resource_id": catalog["Fern Room"],
            "slots": windows([12]),
            "equipment": ["Projector"],
        },
    )
    original = owner.get("/bookings").json()
    for hour in [
        10,
        12,
    ]:  # Room conflict, then equipment shortage with an otherwise free room.
        response = owner.patch(
            f"/bookings/{booking_id}",
            json={"slots": windows([hour]), "equipment": ["Projector"]},
        )
        assert response.status_code == 409
        assert owner.get("/bookings").json() == original
        assert counts(db) == (3, 2)


def test_book_09_cancel_releases_resources_and_prevents_edits(
    owner, other, payload, reserve, db
):
    body = {**payload, "equipment": ["Projector", "Camera"]}
    booking_id = reserve(owner, body)
    assert owner.post(f"/bookings/{booking_id}/cancel").status_code == 204
    assert (
        owner.patch(
            f"/bookings/{booking_id}", json={"slots": body["slots"]}
        ).status_code
        == 409
    )
    with Session(db) as session:
        assert session.get(Booking, booking_id).status == "cancelled"
        assert set(session.scalars(select(BookingEquipment.status))) == {"cancelled"}
    reserve(other, body)


def test_book_10_started_booking_cannot_be_changed(
    owner, payload, windows, reserve, db
):
    booking_id = reserve(owner, payload)
    with Session(db) as session, session.begin():
        set_booking_slots(
            session.get(Booking, booking_id),
            [BookingWindow.model_validate(item) for item in windows([8], offset=-3)],
        )
    original = owner.get("/bookings").json()
    assert (
        owner.patch(
            f"/bookings/{booking_id}", json={"slots": windows([16])}
        ).status_code
        == 409
    )
    assert owner.post(f"/bookings/{booking_id}/cancel").status_code == 409
    assert owner.get("/bookings").json() == original
