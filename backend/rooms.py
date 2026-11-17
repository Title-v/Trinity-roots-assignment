from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_engine
from models import Resource

router = APIRouter(tags=["rooms"])


# Describe the room fields exposed to the frontend catalog.
class RoomSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    image_key: str | None
    capacity: int | None


@router.get("/rooms")
# Return active rooms with capacity and image references for browsing.
def list_rooms() -> list[RoomSummary]:
    try:
        with Session(get_engine()) as session:
            rooms = session.scalars(
                select(Resource)
                .where(Resource.kind == "room", Resource.is_active)
                .order_by(Resource.id)
            )
            return [RoomSummary.model_validate(room) for room in rooms]
    except (SQLAlchemyError, ValueError):
        raise HTTPException(503, "Could not load rooms.") from None
