"""Add missing sample equipment units."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_engine
from equipment import EQUIPMENT
from models import Resource

if __name__ == "__main__":
    with Session(get_engine()) as session, session.begin():
        existing = set(
            session.scalars(select(Resource.name).where(Resource.kind == "equipment"))
        )
        units = [
            Resource(name=name, kind="equipment")
            for category, quantity in EQUIPMENT.items()
            for number in range(1, quantity + 1)
            if (name := f"{category} {number:02d}") not in existing
        ]
        session.add_all(units)
    print(f"Added {len(units)} equipment units.")
