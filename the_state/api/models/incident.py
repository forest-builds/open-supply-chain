from datetime import datetime

from core.db import Base
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    incident_number: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String)
    incident_type: Mapped[str] = mapped_column(String, index=True)
    state: Mapped[str] = mapped_column(String(2), index=True)
    status: Mapped[str] = mapped_column(String, default="open")
    declared_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String, default="openfema")
    raw: Mapped[str | None] = mapped_column(String, nullable=True)
