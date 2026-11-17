from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, PositiveInt
from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import Range
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
from equipment import (
    EquipmentItem,
    EquipmentSummary,
    EquipmentType,
    equipment_availability,
    reserve_equipment,
)
from models import Booking, BookingEquipment, Resource

router = APIRouter(tags=["bookings"])
CurrentAccount = Annotated[Account, Depends(me)]


# Describe a single-slot room booking with optional equipment.
class BookingRequest(BookingWindow):
    resource_id: PositiveInt
    party_size: PositiveInt
    equipment: list[EquipmentType] = Field(default_factory=list, max_length=3)


# Add an availability status to a one-hour time window.
class RoomSlot(BookingWindow):
    status: str


# Enforce hourly slots and business hours; writes also require a future start.
def validate_window(window: BookingWindow, *, require_future: bool = True) -> None:
    if not within_business_hours(window):
        raise HTTPException(422, "Choose a time within 08:00–18:00 Bangkok time.")
    start = window.starts_at.astimezone(BOOKING_TIMEZONE)
    if start.time() != start.time().replace(minute=0, second=0, microsecond=0) or (
        window.ends_at - window.starts_at != timedelta(hours=1)
    ):
        raise HTTPException(422, "Choose a one-hour slot starting on the hour.")
    if require_future and window.starts_at <= datetime.now(UTC):
        raise HTTPException(422, "Choose a start time in the future.")


@router.get("/rooms/slots")
# Return availability for rooms that can accommodate the requested group.
def all_room_slots(
    day: date, people: PositiveInt, response: Response
) -> dict[int, list[RoomSlot]]:
    return load_room_slots(day, response, people=people)


@router.get("/rooms/{room_id}/slots")
# Return one room’s slots or report that the room is no longer listed.
def room_slots(room_id: int, day: date, response: Response) -> list[RoomSlot]:
    result = load_room_slots(day, response, room_id=room_id)
    if room_id not in result:
        raise HTTPException(404, "This room is no longer listed.")
    return result[room_id]


# Read confirmed reservations and turn their actual ranges into hourly room availability.
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
        select(Resource.id, Booking.time_ranges)
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
        for resource_id, time_ranges in session.execute(query):
            bookings = bookings_by_room.setdefault(resource_id, [])
            if time_ranges is not None:
                for period in time_ranges:
                    assert period.lower is not None and period.upper is not None
                    bookings.append((period.lower, period.upper))

    return {
        resource_id: build_slots(opens, closes, now, bookings)
        for resource_id, bookings in bookings_by_room.items()
    }


# Mark each hourly slot as past, booked, or available; touching boundaries do not overlap.
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


# Describe replacement slots; omitted equipment preserves the current selection during edits.
class BookingSlots(BaseModel):
    slots: list[BookingWindow] = Field(min_length=1, max_length=10)
    equipment: list[EquipmentType] | None = Field(default=None, max_length=3)


# Group selected hourly slots into one room reservation and equipment allocation.
class BookingBatch(BookingSlots):
    resource_id: PositiveInt
    party_size: PositiveInt
    equipment: list[EquipmentType] = Field(default_factory=list, max_length=3)


@router.post("/bookings", status_code=201)
# Create a reservation from the single-slot API using the shared transaction helper.
def create_booking(window: BookingRequest, account: CurrentAccount) -> dict[str, int]:
    ids = save_bookings(
        window.resource_id, window.party_size, [window], account, window.equipment
    )
    return {"id": ids[0]}


@router.post("/bookings/batch", status_code=201)
# Create one reservation containing all selected slots, not one booking per hour.
def create_booking_batch(
    request: BookingBatch, account: CurrentAccount
) -> dict[str, list[int]]:
    return {
        "ids": save_bookings(
            request.resource_id,
            request.party_size,
            request.slots,
            account,
            request.equipment,
        )
    }


# Validate room capacity and save the room and equipment together in one transaction.
def save_bookings(
    resource_id: int,
    party_size: int,
    slots: list[BookingWindow],
    account: Account,
    equipment: list[EquipmentType] | None = None,
) -> list[int]:
    slots = validate_slots(slots)

    try:
        with Session(get_engine()) as session, session.begin():
            resource = session.get(Resource, resource_id)
            if resource is None or not resource.is_active:
                raise HTTPException(404, "This room is no longer listed.")
            if resource.kind != "room":
                raise HTTPException(
                    422, "Equipment must be attached to a room booking."
                )
            if resource.capacity is None or party_size > resource.capacity:
                raise HTTPException(422, "This room cannot accommodate your group.")
            booking = Booking(
                resource_id=resource.id,
                user_id=account.id,
                status="confirmed",
            )
            set_booking_slots(booking, slots)
            session.add(booking)
            session.flush()
            if equipment:
                reserve_equipment(session, booking, equipment)
            ids = [booking.id]
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) == "23P01":
            raise HTTPException(
                409,
                "Booking unsuccessful. The room or equipment is no longer available "
                "for the selected time. Please search again for another room or time.",
            ) from None
        raise
    return ids


# Reject duplicate slots and mixed dates, then return the slots in chronological order.
def validate_slots(
    slots: list[BookingWindow], *, require_future: bool = True
) -> list[BookingWindow]:
    for slot in slots:
        validate_window(slot, require_future=require_future)
    starts = {slot.starts_at for slot in slots}
    dates = {start.astimezone(BOOKING_TIMEZONE).date() for start in starts}
    if len(starts) != len(slots) or len(dates) != 1:
        raise HTTPException(422, "Choose distinct slots on the same date.")
    return sorted(slots, key=lambda slot: slot.starts_at)


# Store actual selected ranges while retaining outer start and end fields for display.
def set_booking_slots(booking: Booking, slots: list[BookingWindow]) -> None:
    booking.starts_at = slots[0].starts_at
    booking.ends_at = slots[-1].ends_at
    booking.time_ranges = [Range(slot.starts_at, slot.ends_at) for slot in slots]


# Expand stored ranges into hourly slots without filling gaps between them.
def booking_slots(booking: Booking) -> list[BookingWindow]:
    slots = []
    for period in booking.time_ranges:
        assert period.lower is not None and period.upper is not None
        start = period.lower
        while start < period.upper:
            end = min(start + timedelta(hours=1), period.upper)
            slots.append(BookingWindow(starts_at=start, ends_at=end))
            start = end
    return slots


# Shape the owner’s booking response, including slots, equipment, and available actions.
class MyBooking(BookingWindow):
    id: int
    room_name: str
    image_key: str | None
    status: str
    can_cancel: bool
    slots: list[BookingWindow]
    equipment: list[EquipmentItem]


@router.get("/bookings")
# Fetch only the signed-in account’s bookings and their assigned equipment.
def my_bookings(account: CurrentAccount, response: Response) -> list[MyBooking]:
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(UTC)
    with Session(get_engine()) as session:
        equipment_by_booking: dict[int, list[EquipmentItem]] = {}
        for booking_id, unit in session.execute(
            select(BookingEquipment.booking_id, Resource)
            .join(Resource, Resource.id == BookingEquipment.resource_id)
            .join(Booking, Booking.id == BookingEquipment.booking_id)
            .where(Booking.user_id == account.id)
            .order_by(Resource.name)
        ):
            equipment_by_booking.setdefault(booking_id, []).append(
                EquipmentItem.model_validate(
                    {
                        "id": unit.id,
                        "name": unit.name,
                        "category": unit.name.split(" ", 1)[0],
                    }
                )
            )
        rows = session.execute(
            select(Booking, Resource.name, Resource.image_key)
            .join(Resource)
            .where(Booking.user_id == account.id)
            .order_by(Booking.starts_at.desc(), Booking.id.desc())
        )
        return [
            MyBooking(
                id=booking.id,
                room_name=name,
                image_key=image_key,
                starts_at=booking.starts_at,
                ends_at=booking.ends_at,
                status=booking.status,
                can_cancel=booking.status == "confirmed" and booking.starts_at > now,
                slots=booking_slots(booking),
                equipment=equipment_by_booking.get(booking.id, []),
            )
            for booking, name, image_key in rows
        ]


@router.post("/bookings/{booking_id}/cancel", status_code=204)
# Cancel an owned future reservation and release its room and equipment together.
def cancel_booking(booking_id: PositiveInt, account: CurrentAccount) -> Response:
    with Session(get_engine()) as session, session.begin():
        booking = lock_owned_booking(session, booking_id, account)
        if booking.status not in {"confirmed", "cancelled"} or (
            booking.status == "confirmed" and booking.starts_at <= datetime.now(UTC)
        ):
            raise HTTPException(
                409, "Only bookings that have not started can be cancelled."
            )
        booking.status = "cancelled"
        # Keep every linked reservation in sync, including repeated cancellations.
        session.execute(
            update(BookingEquipment)
            .where(BookingEquipment.booking_id == booking.id)
            .values(status=booking.status)
        )
    return Response(status_code=204)


# Check ownership and lock the booking row to serialize edits and cancellations.
def lock_owned_booking(session: Session, booking_id: int, account: Account) -> Booking:
    booking = session.scalar(
        select(Booking)
        .where(Booking.id == booking_id, Booking.user_id == account.id)
        .with_for_update()
    )
    if booking is None:
        raise HTTPException(404, "Booking not found.")
    return booking


@router.patch("/bookings/{booking_id}", status_code=204)
# Replace an owned booking’s slots and equipment atomically; conflicts retain the old state.
def reschedule_booking(
    booking_id: PositiveInt,
    window: BookingSlots | BookingWindow,
    account: CurrentAccount,
) -> Response:
    try:
        with Session(get_engine()) as session, session.begin():
            booking = lock_owned_booking(session, booking_id, account)
            if booking.status != "confirmed" or booking.starts_at <= datetime.now(UTC):
                raise HTTPException(
                    409, "Only confirmed bookings that have not started can be edited."
                )
            slots = validate_slots(
                window.slots if isinstance(window, BookingSlots) else [window]
            )
            resource = session.get(Resource, booking.resource_id)
            if resource is None or resource.kind != "room" or not resource.is_active:
                raise HTTPException(
                    409, "This room is no longer available for booking."
                )
            set_booking_slots(booking, slots)
            selected_equipment = (
                window.equipment if isinstance(window, BookingSlots) else None
            )
            if selected_equipment is None:
                names = session.scalars(
                    select(Resource.name)
                    .join(BookingEquipment, BookingEquipment.resource_id == Resource.id)
                    .where(BookingEquipment.booking_id == booking.id)
                ).all()
                selected_equipment = [name.split(" ", 1)[0] for name in names]
            reserve_equipment(session, booking, selected_equipment)
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) == "23P01":
            raise HTTPException(
                409, "The room or equipment is already booked. Choose another time."
            ) from None
        raise
    return Response(status_code=204)


@router.post("/equipment/availability", tags=["equipment"])
# Read equipment availability for a proposed selection without reserving units.
def check_equipment(
    request: BookingSlots, response: Response
) -> list[EquipmentSummary]:
    slots = validate_slots(request.slots)
    response.headers["Cache-Control"] = "no-store"
    with Session(get_engine()) as session:
        return equipment_availability(
            session, [Range(slot.starts_at, slot.ends_at) for slot in slots]
        )


@router.post("/bookings/{booking_id}/equipment-availability")
# Check an owner’s edit while excluding that booking’s current equipment allocation.
def check_booking_equipment(
    booking_id: PositiveInt,
    request: BookingSlots,
    response: Response,
    account: CurrentAccount,
) -> list[EquipmentSummary]:
    response.headers["Cache-Control"] = "no-store"
    with Session(get_engine()) as session:
        booking = session.scalar(
            select(Booking).where(
                Booking.id == booking_id, Booking.user_id == account.id
            )
        )
        if booking is None:
            raise HTTPException(404, "Booking not found.")
        slots = validate_slots(request.slots)
        return equipment_availability(
            session,
            [Range(slot.starts_at, slot.ends_at) for slot in slots],
            exclude_booking_id=booking.id,
        )
