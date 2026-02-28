import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    plaid_link_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plaid_links.id"), nullable=False)
    plaid_account_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    official_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # depository, credit, loan, investment
    subtype: Mapped[str | None] = mapped_column(String(50), nullable=True)  # checking, savings, credit card, etc.
    balance_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    balance_available: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    last_synced: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    balance_manual: Mapped[float | None] = mapped_column(Float, nullable=True)
    balance_manual_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_hidden: Mapped[bool] = mapped_column(default=False)

    user: Mapped["User"] = relationship(back_populates="accounts")
    plaid_link: Mapped["PlaidLink"] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account", cascade="all, delete-orphan")
