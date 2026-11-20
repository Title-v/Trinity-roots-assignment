from datetime import datetime, time

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSTZMULTIRANGE, ExcludeConstraint, Range
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# Share SQLAlchemy metadata used by the ORM and Alembic migrations.
class Base(DeclarativeBase):
    pass


# Store account identities and password hashes, never plaintext passwords.
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))


# Represent a room or an individual equipment unit in the shared catalog.
class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_resources_capacity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(50))
    capacity: Mapped[int | None]
    image_key: Mapped[str | None] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(server_default="true")


# Reserve schema support for per-resource schedules; current runtime uses shared hours.
class AvailabilityRule(Base):
    __tablename__ = "availability_rules"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_availability_weekday"),
        CheckConstraint("opens_at < closes_at", name="ck_availability_time_order"),
        UniqueConstraint(
            "resource_id",
            "weekday",
            "opens_at",
            "closes_at",
            name="uq_availability_resource_window",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"))
    weekday: Mapped[int]  # Monday is 0, Sunday is 6.
    opens_at: Mapped[time]
    closes_at: Mapped[time]


# Store one reservation with potentially separated time ranges and a lifecycle status.
class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("starts_at < ends_at", name="ck_bookings_time_order"),
        CheckConstraint(
            "status IN ('confirmed', 'cancelled', 'completed')",
            name="ck_bookings_status",
        ),
        CheckConstraint(
            "NOT isempty(time_ranges) AND NOT lower_inf(time_ranges) "
            "AND NOT upper_inf(time_ranges) AND lower(time_ranges) = starts_at "
            "AND upper(time_ranges) = ends_at",
            name="ck_bookings_range_bounds",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    time_ranges: Mapped[list[Range[datetime]]] = mapped_column(TSTZMULTIRANGE)
    status: Mapped[str] = mapped_column(String(16), server_default="confirmed")
    version: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# Link a physical unit to the room booking and prevent overlapping confirmed allocations.
class BookingEquipment(Base):
    __tablename__ = "booking_equipment"
    __table_args__ = (
        UniqueConstraint("booking_id", "resource_id", name="uq_booking_equipment_unit"),
        CheckConstraint(
            "status IN ('confirmed', 'cancelled', 'completed')",
            name="ck_booking_equipment_status",
        ),
        CheckConstraint(
            "NOT isempty(time_ranges) AND NOT lower_inf(time_ranges) AND NOT upper_inf(time_ranges)",
            name="ck_booking_equipment_ranges",
        ),
        ExcludeConstraint(
            ("resource_id", "="),
            ("time_ranges", "&&"),
            where=text("status = 'confirmed'"),
            using="gist",
            name="booking_equipment_no_overlap",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE")
    )
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"))
    time_ranges: Mapped[list[Range[datetime]]] = mapped_column(TSTZMULTIRANGE)
    status: Mapped[str] = mapped_column(String(16))


# Durable model request/response logs for hosts without persistent local disk.
class AssistantAuditLog(Base):
    __tablename__ = "assistant_audit_logs"
    __table_args__ = (
        CheckConstraint(
            "event IN ('request', 'response')", name="ck_assistant_audit_event"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(32), index=True)
    event: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
