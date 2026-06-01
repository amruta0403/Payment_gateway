from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models.payment import Transaction, TransactionEvent
from shared.exceptions.handlers import InvalidTransitionError
from shared.models.enums import TransactionStatus


class PaymentStateMachine:
    ALLOWED_TRANSITIONS: dict[TransactionStatus, list[TransactionStatus]] = {
        TransactionStatus.CREATED: [
            TransactionStatus.PENDING,
            TransactionStatus.FAILED,
            TransactionStatus.CANCELLED,
        ],
        TransactionStatus.PENDING: [
            TransactionStatus.PROCESSING,
            TransactionStatus.FAILED,
            TransactionStatus.CANCELLED,
        ],
        TransactionStatus.PROCESSING: [
            TransactionStatus.AUTHORIZED,
            TransactionStatus.CAPTURED,
            TransactionStatus.FAILED,
        ],
        TransactionStatus.AUTHORIZED: [
            TransactionStatus.CAPTURED,
            TransactionStatus.CANCELLED,
            TransactionStatus.FAILED,
        ],
        TransactionStatus.CAPTURED: [
            TransactionStatus.SETTLEMENT_INITIATED,
            TransactionStatus.REFUNDED,
            TransactionStatus.PARTIALLY_REFUNDED,
            TransactionStatus.DISPUTED,
        ],
        TransactionStatus.SETTLEMENT_INITIATED: [
            TransactionStatus.SETTLED,
            TransactionStatus.FAILED,
        ],
        TransactionStatus.SETTLED: [
            TransactionStatus.REFUNDED,
            TransactionStatus.PARTIALLY_REFUNDED,
            TransactionStatus.DISPUTED,
        ],
        TransactionStatus.PARTIALLY_REFUNDED: [
            TransactionStatus.REFUNDED,
            TransactionStatus.DISPUTED,
        ],
        TransactionStatus.FAILED: [],
        TransactionStatus.CANCELLED: [],
        TransactionStatus.REFUNDED: [],
        TransactionStatus.DISPUTED: [],
        TransactionStatus.CHARGEBACK: [],
    }

    _TIMESTAMP_FIELDS: dict[TransactionStatus, str] = {
        TransactionStatus.AUTHORIZED: "authorized_at",
        TransactionStatus.CAPTURED: "captured_at",
        TransactionStatus.SETTLED: "settled_at",
        TransactionStatus.FAILED: "failed_at",
        TransactionStatus.CANCELLED: "cancelled_at",
    }

    @classmethod
    async def transition(
        cls,
        payment: Transaction,
        new_status: TransactionStatus,
        db: AsyncSession,
        triggered_by: str,
        actor_id: uuid.UUID | None = None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Transaction:
        allowed = cls.ALLOWED_TRANSITIONS.get(payment.status, [])
        if new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition {payment.status.value} → {new_status.value}. "
                f"Allowed: {[s.value for s in allowed] or 'none (terminal state)'}"
            )

        old_status = payment.status
        payment.status = new_status

        ts_field = cls._TIMESTAMP_FIELDS.get(new_status)
        if ts_field:
            setattr(payment, ts_field, datetime.now(timezone.utc))

        event = TransactionEvent(
            transaction_id=payment.id,
            from_status=old_status,
            to_status=new_status,
            triggered_by=triggered_by,
            actor_id=actor_id,
            message=message,
            metadata=metadata or {},
        )
        db.add(event)
        await db.flush()

        return payment
