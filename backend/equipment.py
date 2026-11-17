from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_engine
from models import Booking, BookingEquipment, Resource

router = APIRouter(tags=["equipment"])
EQUIPMENT = {"Projector": 8, "Camera": 5, "Microphone": 5}
EquipmentType = Literal["Projector", "Camera", "Microphone"]


class EquipmentSummary(BaseModel):
    name: str
    quantity: int


class EquipmentItem(BaseModel):
    id: int
    name: str
    category: EquipmentType


def available_equipment(
    session: Session,
    time_ranges: list[Range[datetime]],
    *,
    exclude_booking_id: int | None = None,
) -> list[Resource]:
    reserved = select(BookingEquipment.resource_id).where(
        BookingEquipment.status == "confirmed",
        BookingEquipment.time_ranges.overlaps(time_ranges),
    )
    if exclude_booking_id is not None:
        reserved = reserved.where(BookingEquipment.booking_id != exclude_booking_id)
    return list(
        session.scalars(
            select(Resource)
            .where(
                Resource.kind == "equipment",
                Resource.is_active,
                Resource.id.not_in(reserved),
            )
            .order_by(Resource.id)
        )
    )


def equipment_availability(
    session: Session,
    time_ranges: list[Range[datetime]],
    *,
    exclude_booking_id: int | None = None,
) -> list[EquipmentSummary]:
    units = available_equipment(
        session, time_ranges, exclude_booking_id=exclude_booking_id
    )
    return [
        EquipmentSummary(
            name=category,
            quantity=sum(unit.name.split(" ", 1)[0] == category for unit in units),
        )
        for category in EQUIPMENT
    ]


def reserve_equipment(
    session: Session, booking: Booking, categories: list[EquipmentType]
) -> None:
    """Attach equipment using the confirmed room booking's times and status."""
    room = session.get(Resource, booking.resource_id)
    if (
        booking.id is None
        or room is None
        or room.kind != "room"
        or booking.status != "confirmed"
    ):
        raise HTTPException(409, "Equipment requires a confirmed room booking.")
    if len(categories) != len(set(categories)):
        raise HTTPException(422, "Select each equipment type once.")

    # Lock inventory in a consistent order before checking for free units.
    session.execute(
        select(Resource.id)
        .where(
            Resource.kind == "equipment",
            func.split_part(Resource.name, " ", 1).in_(categories),
        )
        .order_by(Resource.id)
        .with_for_update()
    ).all()
    units = (
        available_equipment(session, booking.time_ranges, exclude_booking_id=booking.id)
        if categories
        else []
    )
    reservations = []
    for category in categories:
        unit = next(
            (unit for unit in units if unit.name.split(" ", 1)[0] == category), None
        )
        if unit is None:
            raise HTTPException(
                409, f"No {category.lower()} is available for all selected times."
            )
        reservations.append(
            BookingEquipment(
                booking_id=booking.id,
                resource_id=unit.id,
                time_ranges=booking.time_ranges,
                status=booking.status,
            )
        )
    session.execute(
        delete(BookingEquipment).where(BookingEquipment.booking_id == booking.id)
    )
    session.add_all(reservations)


@router.get("/equipment")
def list_equipment() -> list[EquipmentSummary]:
    category = func.split_part(Resource.name, " ", 1)
    try:
        with Session(get_engine()) as session:
            counts = dict(
                session.execute(
                    select(category, func.count())
                    .where(Resource.kind == "equipment", Resource.is_active)
                    .group_by(category)
                ).all()
            )
    except (SQLAlchemyError, ValueError):
        raise HTTPException(503, "Could not load equipment.") from None
    return [
        EquipmentSummary(name=name, quantity=counts.get(name, 0)) for name in EQUIPMENT
    ]
