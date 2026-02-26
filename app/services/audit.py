from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_content
from app.models.incident import AuditEntry


async def write_audit(
    db: AsyncSession,
    *,
    session_id: str,
    actor_id: str,
    step: str,
    input_data: str,
    output_data: str,
    incident_id: UUID | None = None,
) -> None:
    entry = AuditEntry(
        id=uuid.uuid4(),
        incident_id=incident_id,
        session_id=session_id,
        actor_id=actor_id,
        step=step,
        input_hash=hash_content(input_data),
        output_hash=hash_content(output_data),
    )
    db.add(entry)
    await db.flush()
