from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DatabaseSettings(BaseSettings):
    database_url: str

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.local"),
        extra="ignore",
        hide_input_in_errors=True,
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = make_url(DatabaseSettings().database_url)
    if url.get_backend_name() not in {"postgresql", "postgres"}:
        raise ValueError("DATABASE_URL must be a PostgreSQL URL")
    return create_engine(
        url.set(drivername="postgresql+psycopg"),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )
