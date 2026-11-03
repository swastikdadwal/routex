from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (CheckConstraint("capacity > 0"), CheckConstraint("cost_per_km >= 0"))

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    capacity: Mapped[int] = mapped_column(Integer)
    cost_per_km: Mapped[float] = mapped_column(Float, default=1.0)
    active: Mapped[bool] = mapped_column(default=True)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (CheckConstraint("demand > 0"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    demand: Mapped[int] = mapped_column(Integer)


class Run(Base):
    """One comparison. The scenario is a snapshot, so a past run stays accurate
    after its orders or vehicles are edited or deleted."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    scenario: Mapped[dict] = mapped_column(JSONB)
    algorithms: Mapped[list] = mapped_column(JSONB)
    requested_source: Mapped[str] = mapped_column(String(20))
    distance_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    time_limit_s: Mapped[float] = mapped_column(Float)
    lower_bound_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    path_stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notice: Mapped[str | None] = mapped_column(String(500), nullable=True)

    results: Mapped[list["RunResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="RunResult.id"
    )


class RunResult(Base):
    __tablename__ = "run_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    algorithm: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    elapsed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    work: Mapped[int | None] = mapped_column(Integer, nullable=True)
    routes: Mapped[list] = mapped_column(JSONB, default=list)
    unserved: Mapped[list] = mapped_column(JSONB, default=list)

    run: Mapped[Run] = relationship(back_populates="results")


class Benchmark(Base):
    __tablename__ = "benchmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(20), default="running")
    progress: Mapped[dict] = mapped_column(JSONB, default=dict)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    rows: Mapped[list] = mapped_column(JSONB, default=list)
