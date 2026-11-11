from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_engine
from models import Resource

router = APIRouter(tags=["equipment"])
EQUIPMENT = {"Projector": 8, "Camera": 5, "Microphone": 5}


class EquipmentSummary(BaseModel):
    name: str
    quantity: int


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
