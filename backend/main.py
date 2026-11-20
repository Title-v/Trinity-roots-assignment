import os

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from assistant import router as assistant_router
from auth import router as auth_router
from availability import router as availability_router
from bookings import router as bookings_router
from database import get_engine
from equipment import router as equipment_router
from rooms import router as rooms_router

app = FastAPI(
    title="Resource Booking API",
    root_path=os.getenv("API_ROOT_PATH", ""),
)
app.include_router(auth_router)
app.include_router(assistant_router)
app.include_router(availability_router)
app.include_router(rooms_router)
app.include_router(bookings_router)
app.include_router(equipment_router)


@app.get("/health")
# Check that the API process responds without requiring a database connection.
def health_check():
    return {"status": "ok"}


@app.get("/health/db")
# Run a small database query and return a safe error if storage is unavailable.
def database_health_check():
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
    except (SQLAlchemyError, ValueError):
        raise HTTPException(503, "Database connection unavailable") from None

    return {"status": "ok", "database": "connected"}
