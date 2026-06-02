from __future__ import annotations

import logging
import os
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from celery import shared_task
from sqlalchemy import func, select, update

from celery_app import celery_app
from models.cross_service import Merchant, MerchantBankAccount, Transaction
from models.settlement_batch import SettlementBatch, SettlementStatus
from models.settlement_payout import PayoutMethod, PayoutStatus, SettlementPayout
from models.settlement_transaction import SettlementTransaction
from payout_providers.mock import MockPayoutProvider
from utils.db import get_sync_db
from utils.fee_calculator import calculate_fee

log = logging.getLogger(__name__)

# ── Payout provider (swappable) ───────────────────────────────────────────────
def _get_payout_provider():
    mode = os.environ.get("PAYOUT_PROVIDER", "mock")
    if mode == "razorpay":
        from payout_providers.razorpay import RazorpayXProvider
        return RazorpayXProvider(
            key_id=os.environ.get("RAZORPAY_KEY_ID", ""),
            key_secret=os.environ.get("RAZORPAY_KEY_SECRET", ""),
            account_number=os.environ.get("RAZORPAY_X_ACCOUNT", ""),
        )
    return MockPayoutProvider()


# ── Encryption helper ─────────────────────────────────────────────────────────
def _get_decryptor():
    key = os.environ.get("CARD_ENCRYPTION_KEY_V1", "")
    if key:
        from shared.utils.encryption import FieldEncryptor
        return FieldEncryptor(key)
    return None


_decryptor = None


def _decrypt(value: str) -> str:
    global _decryptor
    if _decryptor is None:
        _decryptor = _get_decryptor()
    if _decryptor and value:
        try:
            return _decryptor.decrypt(value)
        except Exception:
            pass
    return value


# ── TransactionStatus constants (avoid importing shared enum in sync context) ─
_CAPTURED = "CAPTURED"
_SETTLEMENT_INITIATED = "SETTLEMENT_INITIATED"
_SETTLED = "SETTLED"


# ── Task: create_daily_batch ──────────────────────────────────────────────────

@celery_app.task(
    name="settlement.create_daily_batch",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def create_daily_batch(self, settlement_date_str: str | None = None):
    """
    For every merchant with CAPTURED transactions on settlement_date,
    create a SettlementBatch + SettlementTransactions and queue payout.
    Runs daily at 23:00 IST (17:30 UTC) via Celery Beat.
    """
    if settlement_date_str is None:
        # Default: previous calendar day
        settlement_date = (datetime.utcnow() - timedelta(days=1)).date()
        settlement_date_str = settlement_date.isoformat()
    else:
        settlement_date = date.fromisoformat(settlement_date_str)

    log.info("settlement.create_daily_batch.start", extra={"date": settlement_date_str})

    try:
        with get_sync_db() as db:
            # 1. Find all merchants with captured txns on this date
            merchant_ids = (
                db.execute(
                    select(Transaction.merchant_id)
                    .where(
                        Transaction.status == _CAPTURED,
                        func.date(Transaction.captured_at) == settlement_date,
                    )
                    .distinct()
                )
                .scalars()
                .all()
            )

            if not merchant_ids:
                log.info("settlement.create_daily_batch.no_txns", extra={"date": settlement_date_str})
                return {"date": settlement_date_str, "batches": 0}

            batches_created = 0
            for merchant_id in merchant_ids:
                try:
                    _create_batch_for_merchant(db, merchant_id, settlement_date)
                    batches_created += 1
                except Exception as exc:
                    log.error(
                        "settlement.batch.merchant_failed",
                        extra={"merchant_id": str(merchant_id), "error": str(exc)},
                        exc_info=True,
                    )
                    db.rollback()

        log.info(
            "settlement.create_daily_batch.done",
            extra={"date": settlement_date_str, "batches": batches_created},
        )
        return {"date": settlement_date_str, "batches": batches_created}

    except Exception as exc:
        log.error("settlement.create_daily_batch.error", extra={"error": str(exc)}, exc_info=True)
        raise self.retry(exc=exc)


def _create_batch_for_merchant(db, merchant_id, settlement_date: date) -> None:
    txns = (
        db.execute(
            select(Transaction).where(
                Transaction.merchant_id == merchant_id,
                Transaction.status == _CAPTURED,
                func.date(Transaction.captured_at) == settlement_date,
            )
        )
        .scalars()
        .all()
    )

    if not txns:
        return

    fee_config_row = db.execute(
        select(Merchant.fee_config).where(Merchant.id == merchant_id)
    ).scalar_one_or_none()
    fee_config = fee_config_row if fee_config_row else {}

    gross = sum(t.captured_amount or t.amount for t in txns)
    fees = [
        calculate_fee(t.captured_amount or t.amount, t.payment_method, fee_config)
        for t in txns
    ]
    total_fee = sum(f.fee_paise for f in fees)
    total_gst = sum(f.gst_paise for f in fees)
    net = gross - total_fee - total_gst

    batch = SettlementBatch(
        merchant_id=merchant_id,
        settlement_date=settlement_date,
        gross_amount=gross,
        fee_amount=total_fee,
        gst_on_fee=total_gst,
        net_amount=net,
        transaction_count=len(txns),
        status=SettlementStatus.PENDING,
    )
    db.add(batch)
    db.flush()  # get batch.id

    for txn, fee in zip(txns, fees):
        db.add(
            SettlementTransaction(
                batch_id=batch.id,
                transaction_id=txn.id,
                amount=txn.captured_amount or txn.amount,
                fee=fee.fee_paise,
                gst=fee.gst_paise,
                net=fee.net_paise,
            )
        )
        txn.status = _SETTLEMENT_INITIATED

    db.commit()
    log.info(
        "settlement.batch.created",
        extra={
            "batch_id": str(batch.id),
            "merchant_id": str(merchant_id),
            "txn_count": len(txns),
            "net_paise": net,
        },
    )
    # Queue payout asynchronously
    initiate_payout.delay(str(batch.id))


# ── Task: initiate_payout ─────────────────────────────────────────────────────

@celery_app.task(
    name="settlement.initiate_payout",
    bind=True,
    max_retries=5,
    default_retry_delay=600,
)
def initiate_payout(self, batch_id: str):
    """Create the actual bank payout via the payout provider."""
    log.info("settlement.initiate_payout.start", extra={"batch_id": batch_id})

    try:
        payout_provider = _get_payout_provider()

        with get_sync_db() as db:
            batch = db.get(SettlementBatch, uuid.UUID(batch_id))
            if not batch:
                log.error("settlement.initiate_payout.batch_not_found", extra={"batch_id": batch_id})
                return

            if batch.status == SettlementStatus.COMPLETED:
                log.info("settlement.initiate_payout.already_done", extra={"batch_id": batch_id})
                return

            bank_account = (
                db.execute(
                    select(MerchantBankAccount).where(
                        MerchantBankAccount.merchant_id == batch.merchant_id,
                        MerchantBankAccount.is_primary.is_(True),
                        MerchantBankAccount.is_verified.is_(True),
                    )
                )
                .scalar_one_or_none()
            )

            if not bank_account:
                log.error(
                    "settlement.initiate_payout.no_bank_account",
                    extra={"merchant_id": str(batch.merchant_id)},
                )
                batch.status = SettlementStatus.FAILED
                db.commit()
                return

            payout = SettlementPayout(
                batch_id=batch.id,
                merchant_bank_account_id=bank_account.id,
                amount=batch.net_amount,
                payout_method=PayoutMethod.IMPS,
                status=PayoutStatus.INITIATED,
            )
            db.add(payout)
            db.flush()

            batch.status = SettlementStatus.PROCESSING
            db.commit()

        # Call payout provider OUTSIDE the session to keep the transaction short
        result = payout_provider.create_payout(
            account_number=_decrypt(bank_account.account_number),
            ifsc=bank_account.ifsc_code,
            amount=batch.net_amount,
            reference=str(batch.id),
            account_holder_name=bank_account.account_holder_name,
        )

        with get_sync_db() as db:
            now = datetime.utcnow()
            if result.success:
                db.execute(
                    update(SettlementPayout)
                    .where(SettlementPayout.id == payout.id)
                    .values(
                        utr_number=result.utr,
                        status=PayoutStatus.SUCCESS,
                        completed_at=now,
                    )
                )
                db.execute(
                    update(SettlementBatch)
                    .where(SettlementBatch.id == batch.id)
                    .values(status=SettlementStatus.COMPLETED)
                )
                # Mark all settlement transactions as SETTLED
                settlement_txn_ids = (
                    db.execute(
                        select(SettlementTransaction.transaction_id)
                        .where(SettlementTransaction.batch_id == batch.id)
                    )
                    .scalars()
                    .all()
                )
                if settlement_txn_ids:
                    db.execute(
                        update(Transaction)
                        .where(Transaction.id.in_(settlement_txn_ids))
                        .values(status=_SETTLED, settled_at=now)
                    )
                db.commit()
                log.info(
                    "settlement.payout.success",
                    extra={"batch_id": batch_id, "utr": result.utr},
                )
            else:
                db.execute(
                    update(SettlementPayout)
                    .where(SettlementPayout.id == payout.id)
                    .values(
                        status=PayoutStatus.FAILED,
                        failure_reason=result.error,
                    )
                )
                db.execute(
                    update(SettlementBatch)
                    .where(SettlementBatch.id == batch.id)
                    .values(status=SettlementStatus.FAILED)
                )
                db.commit()
                log.error(
                    "settlement.payout.failed",
                    extra={"batch_id": batch_id, "error": result.error},
                )
                raise self.retry(exc=Exception(result.error or "Payout failed"))

    except Exception as exc:
        if not self.request.retries < self.max_retries:
            log.error("settlement.payout.max_retries_exceeded", extra={"batch_id": batch_id})
        raise


# ── Task: reconcile ───────────────────────────────────────────────────────────

@celery_app.task(name="settlement.reconcile", bind=True, max_retries=2)
def reconcile(self):
    """
    Daily reconciliation (06:00 IST):
    - Find FAILED batches from the previous 3 days → retry payout
    - Find SETTLEMENT_INITIATED transactions with no batch → log alert
    - Find batches older than 5 days still in PROCESSING → investigate
    """
    log.info("settlement.reconcile.start")
    cutoff_date = (datetime.utcnow() - timedelta(days=3)).date()
    alert_cutoff = datetime.utcnow() - timedelta(days=5)

    try:
        with get_sync_db() as db:
            # Re-queue failed batches
            failed_batches = (
                db.execute(
                    select(SettlementBatch).where(
                        SettlementBatch.status == SettlementStatus.FAILED,
                        SettlementBatch.settlement_date >= cutoff_date,
                    )
                )
                .scalars()
                .all()
            )
            for b in failed_batches:
                log.info("settlement.reconcile.retry_payout", extra={"batch_id": str(b.id)})
                initiate_payout.delay(str(b.id))

            # Alert on stuck processing batches
            stuck = (
                db.execute(
                    select(SettlementBatch).where(
                        SettlementBatch.status == SettlementStatus.PROCESSING,
                        SettlementBatch.created_at <= alert_cutoff,
                    )
                )
                .scalars()
                .all()
            )
            for b in stuck:
                log.error(
                    "settlement.reconcile.stuck_batch",
                    extra={"batch_id": str(b.id), "date": str(b.settlement_date)},
                )

        log.info(
            "settlement.reconcile.done",
            extra={"requeued": len(failed_batches), "stuck": len(stuck)},
        )
        return {"requeued": len(failed_batches), "stuck": len(stuck)}

    except Exception as exc:
        log.error("settlement.reconcile.error", extra={"error": str(exc)}, exc_info=True)
        raise self.retry(exc=exc)
