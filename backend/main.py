from database import get_engine
from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

app = FastAPI(title="Resource Booking API")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/health/db")
def database_health_check():
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
    except (SQLAlchemyError, ValueError):
        raise HTTPException(503, "Database connection unavailable") from None

    return {"status": "ok", "database": "connected"}
