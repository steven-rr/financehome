import uuid

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log_event(
    db: AsyncSession,
    event_type: str,
    request: Request,
    user_id: uuid.UUID | None = None,
    details: dict | None = None,
) -> None:
    entry = AuditLog(
        user_id=user_id,
        event_type=event_type,
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent", "") or "")[:512] or None,
        details=details,
    )
    db.add(entry)
    await db.commit()
