from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, PositiveInt
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import Account, me
from availability import (
    BOOKING_TIMEZONE,
    CLOSES_AT,
    OPENS_AT,
    BookingWindow,
    within_business_hours,
)
from database import get_engine
from models import Booking, Resource

router = APIRouter(tags=["bookings"])
CurrentAccount = Annotated[Account, Depends(me)]


class BookingRequest(BookingWindow):
    resource_id: PositiveInt
    party_size: PositiveInt


class RoomSlot(BookingWindow):
    status: str


def validate_window(window: BookingWindow) -> None:
    if not within_business_hours(window):
        raise HTTPException(422, "Choose a time within 08:00–18:00 Bangkok time.")
    start = window.starts_at.astimezone(BOOKING_TIMEZONE)
    if start.time() != start.time().replace(minute=0, second=0, microsecond=0) or (
        window.ends_at - window.starts_at != timedelta(hours=1)
    ):
        raise HTTPException(422, "Choose a one-hour slot starting on the hour.")
    if window.starts_at <= datetime.now(UTC):
        raise HTTPException(422, "Choose a start time in the future.")


@router.get("/rooms/slots")
def all_room_slots(
    day: date, people: PositiveInt, response: Response
) -> dict[int, list[RoomSlot]]:
    return load_room_slots(day, response, people=people)


@router.get("/rooms/{room_id}/slots")
def room_slots(room_id: int, day: date, response: Response) -> list[RoomSlot]:
    result = load_room_slots(day, response, room_id=room_id)
    if room_id not in result:
        raise HTTPException(404, "This room is no longer listed.")
    return result[room_id]


def load_room_slots(
    day: date,
    response: Response,
    *,
    people: int | None = None,
    room_id: int | None = None,
) -> dict[int, list[RoomSlot]]:
    opens = datetime.combine(day, OPENS_AT, BOOKING_TIMEZONE)
    closes = datetime.combine(day, CLOSES_AT, BOOKING_TIMEZONE)
    now = datetime.now(BOOKING_TIMEZONE)
    response.headers["Cache-Control"] = "no-store"
    query = (
        select(Resource.id, Booking.starts_at, Booking.ends_at)
        .outerjoin(
            Booking,
            and_(
                Booking.resource_id == Resource.id,
                Booking.status == "confirmed",
                Booking.starts_at < closes,
                Booking.ends_at > opens,
            ),
        )
        .where(Resource.kind == "room", Resource.is_active)
    )
    if people is not None:
        query = query.where(Resource.capacity >= people)
    if room_id is not None:
        query = query.where(Resource.id == room_id)

    bookings_by_room: dict[int, list[tuple[datetime, datetime]]] = {}
    with Session(get_engine()) as session:
        for resource_id, start, end in session.execute(query):
            bookings = bookings_by_room.setdefault(resource_id, [])
            if start is not None and end is not None:
                bookings.append((start, end))

    return {
        resource_id: build_slots(opens, closes, now, bookings)
        for resource_id, bookings in bookings_by_room.items()
    }


def build_slots(
    opens: datetime,
    closes: datetime,
    now: datetime,
    bookings: list[tuple[datetime, datetime]],
) -> list[RoomSlot]:
    slots = []
    start = opens
    while start < closes:
        end = start + timedelta(hours=1)
        if start <= now:
            status = "past"
        elif any(
            booked_start < end and booked_end > start
            for booked_start, booked_end in bookings
        ):
            status = "booked"
        else:
            status = "available"
        slots.append(RoomSlot(starts_at=start, ends_at=end, status=status))
        start = end
    return slots


class BookingBatch(BaseModel):
    resource_id: PositiveInt
    party_size: PositiveInt
    slots: list[BookingWindow] = Field(min_length=1, max_length=10)


@router.post("/bookings", status_code=201)
def create_booking(window: BookingRequest, account: CurrentAccount) -> dict[str, int]:
    ids = save_bookings(window.resource_id, window.party_size, [window], account)
    return {"id": ids[0]}


@router.post("/bookings/batch", status_code=201)
def create_booking_batch(
    request: BookingBatch, account: CurrentAccount
) -> dict[str, list[int]]:
    return {
        "ids": save_bookings(
            request.resource_id, request.party_size, request.slots, account
        )
    }


def save_bookings(
    resource_id: int, party_size: int, slots: list[BookingWindow], account: Account
) -> list[int]:
    for slot in slots:
        validate_window(slot)
    starts = {slot.starts_at for slot in slots}
    dates = {start.astimezone(BOOKING_TIMEZONE).date() for start in starts}
    if len(starts) != len(slots) or len(dates) != 1:
        raise HTTPException(422, "Choose distinct slots on the same date.")

    try:
        with Session(get_engine()) as session, session.begin():
            resource = session.get(Resource, resource_id)
            if resource is None or resource.kind != "room" or not resource.is_active:
                raise HTTPException(404, "This room is no longer listed.")
            if resource.capacity is None or party_size > resource.capacity:
                raise HTTPException(422, "This room cannot accommodate your group.")
            bookings = [
                Booking(
                    resource_id=resource.id,
                    user_id=account.id,
                    starts_at=slot.starts_at,
                    ends_at=slot.ends_at,
                    status="confirmed",
                )
                for slot in sorted(slots, key=lambda slot: slot.starts_at)
            ]
            session.add_all(bookings)
            session.flush()
            ids = [booking.id for booking in bookings]
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) == "23P01":
            raise HTTPException(
                409,
                "A selected slot was just booked. Please review the available times.",
            ) from None
        raise
    return ids


class MyBooking(BookingWindow):
    id: int
    room_name: str
    status: str
    can_cancel: bool


@router.get("/bookings")
def my_bookings(account: CurrentAccount, response: Response) -> list[MyBooking]:
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(UTC)
    with Session(get_engine()) as session:
        rows = session.execute(
            select(Booking, Resource.name)
            .join(Resource)
            .where(Booking.user_id == account.id)
            .order_by(Booking.starts_at.desc(), Booking.id.desc())
        )
        return [
            MyBooking(
                id=booking.id,
                room_name=name,
                starts_at=booking.starts_at,
                ends_at=booking.ends_at,
                status=booking.status,
                can_cancel=booking.status == "confirmed" and booking.starts_at > now,
            )
            for booking, name in rows
        ]


@router.post("/bookings/{booking_id}/cancel", status_code=204)
def cancel_booking(booking_id: PositiveInt, account: CurrentAccount) -> Response:
    with Session(get_engine()) as session, session.begin():
        booking = session.scalar(
            select(Booking)
            .where(Booking.id == booking_id, Booking.user_id == account.id)
            .with_for_update()
        )
        if booking is None:
            raise HTTPException(404, "Booking not found.")
        if booking.status == "cancelled":
            return Response(status_code=204)
        if booking.status != "confirmed" or booking.starts_at <= datetime.now(UTC):
            raise HTTPException(
                409, "Only bookings that have not started can be cancelled."
            )
        booking.status = "cancelled"
    return Response(status_code=204)
