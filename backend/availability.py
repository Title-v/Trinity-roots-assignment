from datetime import time
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import AwareDatetime, BaseModel

router = APIRouter(tags=["availability"])
BOOKING_TIMEZONE = ZoneInfo("Asia/Bangkok")
OPENS_AT = time(8)
CLOSES_AT = time(18)


class BookingWindow(BaseModel):
    starts_at: AwareDatetime
    ends_at: AwareDatetime


@router.get("/business-hours")
def business_hours():
    return {
        "opens_at": OPENS_AT.isoformat(timespec="minutes"),
        "closes_at": CLOSES_AT.isoformat(timespec="minutes"),
        "timezone": BOOKING_TIMEZONE.key,
        "days": "daily",
    }


def within_business_hours(window: BookingWindow) -> bool:
    start = window.starts_at.astimezone(BOOKING_TIMEZONE)
    end = window.ends_at.astimezone(BOOKING_TIMEZONE)
    return (
        start.date() == end.date()
        and OPENS_AT <= start.time() < end.time() <= CLOSES_AT
    )


@router.post("/business-hours/check")
def check_business_hours(window: BookingWindow):
    return {"within_business_hours": within_business_hours(window)}
