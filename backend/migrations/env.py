from logging.config import fileConfig

from alembic import context
from pydantic import Field
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url

from database import DatabaseSettings
from models import Base


class MigrationSettings(DatabaseSettings):
    database_url: str = Field(validation_alias="DATABASE_URL_UNPOOLED")


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = make_url(MigrationSettings().database_url).set(drivername="postgresql+psycopg")
target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(
        url, poolclass=pool.NullPool, connect_args={"connect_timeout": 10}
    )
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
