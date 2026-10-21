"""What the administrators have done to the library, kept for the "Админы" page."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, uuid_pk


class AdminEvent(Base):
    """One thing an administrator did: tracks added or deleted, lyrics added or synced.

    A row carries an ``amount`` so that deleting a thousand tracks is one row, not a thousand.
    The administrator is kept as an id only: when the account goes, the numbers it made stay in
    the totals, just without a name.
    """

    __tablename__ = "admin_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
