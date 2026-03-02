import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True
    )

    # Digest settings
    digest_enabled: Mapped[bool] = mapped_column(default=True)
    digest_day: Mapped[str] = mapped_column(String(20), default="monday")

    # Alert settings
    alert_budget_exceeded: Mapped[bool] = mapped_column(default=True)
    alert_large_transaction: Mapped[bool] = mapped_column(default=True)
    alert_large_transaction_threshold: Mapped[float] = mapped_column(Float, default=500.0)
    alert_anomaly: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="notification_preferences")
