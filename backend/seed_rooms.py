"""Add the sample rooms and fill any missing capacity values for them."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_engine
from models import Resource

ROOMS = {
    "Oak": 10,
    "Fern": 8,
    "Cedar": 10,
    "River": 8,
    "Lotus": 6,
    "Ivy": 4,
    "Orchid": 8,
    "Bamboo": 8,
    "Maple": 8,
    "Horizon": 12,
}


if __name__ == "__main__":
    added = 0
    updated = 0
    with Session(get_engine()) as session, session.begin():
        existing_rooms = {
            room.image_key: room
            for room in session.scalars(select(Resource).where(Resource.kind == "room"))
        }
        for name, capacity in ROOMS.items():
            key = f"rooms/{name.lower()}.webp"
            room = existing_rooms.get(key)
            if room is None:
                session.add(
                    Resource(
                        name=f"{name} Room",
                        kind="room",
                        image_key=key,
                        capacity=capacity,
                    )
                )
                added += 1
            elif room.capacity is None:
                room.capacity = capacity
                updated += 1
    print(f"Added {added} rooms. Filled capacity for {updated} existing rooms.")
