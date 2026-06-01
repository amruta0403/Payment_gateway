from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.kyc_document import KycDocument
from models.merchant import Merchant
from shared.exceptions.handlers import PaymentGatewayError
from shared.kafka.topics import Topics
from shared.models.enums import KycDocumentStatus, KycDocumentType, MerchantStatus
from shared.utils.encryption import FieldEncryptor

log = structlog.get_logger()

ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/jpg"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

REQUIRED_DOCS = [
    KycDocumentType.PAN,
    KycDocumentType.CANCELLED_CHEQUE,
]


class KycUploadError(PaymentGatewayError):
    http_status = 400
    code = "KYC_UPLOAD_ERROR"
    message = "KYC document upload failed"


async def upload_document(
    merchant_id: uuid.UUID,
    document_type: KycDocumentType,
    file: UploadFile,
    db: AsyncSession,
    s3_client,
    s3_bucket: str,
    encryptor: FieldEncryptor,
    kafka_producer,
    environment: str = "development",
) -> KycDocument:
    # ── 1. Validate file type ─────────────────────────────────────────────────
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise KycUploadError(f"Invalid file type: {content_type}. Allowed: PDF, JPG, PNG")

    # ── Read file bytes ───────────────────────────────────────────────────────
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise KycUploadError(f"File too large: {len(file_bytes)} bytes. Max: {MAX_FILE_SIZE}")
    if len(file_bytes) == 0:
        raise KycUploadError("Empty file uploaded")

    # ── 2. Compute SHA-256 ────────────────────────────────────────────────────
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # ── 3. Build S3 key and encrypt it ───────────────────────────────────────
    ext = _ext_from_content_type(content_type)
    file_uuid = uuid.uuid4()
    s3_key = f"merchants/{merchant_id}/{document_type.value}/{file_uuid}{ext}"
    s3_key_encrypted = encryptor.encrypt(s3_key)

    # ── 4. Upload to S3/R2 ────────────────────────────────────────────────────
    await _upload_to_s3(s3_client, s3_bucket, s3_key, file_bytes, content_type)

    # ── 5. Insert record ──────────────────────────────────────────────────────
    doc = KycDocument(
        merchant_id=merchant_id,
        document_type=document_type,
        status=KycDocumentStatus.PENDING,
        s3_key_encrypted=s3_key_encrypted,
        file_hash=file_hash,
        file_size_bytes=len(file_bytes),
        mime_type=content_type,
        original_filename=file.filename,
    )
    db.add(doc)
    await db.flush()

    # ── 6. Publish Kafka event ────────────────────────────────────────────────
    if kafka_producer:
        try:
            await kafka_producer.publish(
                Topics.MERCHANT_KYC_DOC_UPLOADED,
                "merchant.kyc_doc_uploaded",
                {"merchant_id": str(merchant_id), "document_id": str(doc.id), "document_type": document_type.value},
                key=str(merchant_id),
            )
        except Exception as exc:
            log.warning("kafka.kyc_doc.failed", error=str(exc))

    await db.commit()

    # ── 7. Auto-approve in development ───────────────────────────────────────
    if environment == "development":
        asyncio.create_task(_auto_approve_dev(doc.id, db, kafka_producer))

    return doc


async def approve_document(
    document_id: uuid.UUID,
    admin_user_id: uuid.UUID,
    db: AsyncSession,
    kafka_producer,
) -> KycDocument:
    doc = await db.get(KycDocument, document_id)
    if not doc:
        raise PaymentGatewayError("KYC document not found")

    doc.status = KycDocumentStatus.VERIFIED
    doc.verified_by = admin_user_id
    doc.verified_at = datetime.now(timezone.utc)
    await db.flush()

    # Check if all required docs verified → activate merchant
    await _maybe_activate_merchant(doc.merchant_id, db, kafka_producer)
    await db.commit()
    return doc


async def reject_document(
    document_id: uuid.UUID,
    admin_user_id: uuid.UUID,
    rejection_reason: str,
    db: AsyncSession,
) -> KycDocument:
    doc = await db.get(KycDocument, document_id)
    if not doc:
        raise PaymentGatewayError("KYC document not found")

    doc.status = KycDocumentStatus.REJECTED
    doc.verified_by = admin_user_id
    doc.verified_at = datetime.now(timezone.utc)
    doc.rejection_reason = rejection_reason
    await db.commit()
    return doc


async def _maybe_activate_merchant(
    merchant_id: uuid.UUID,
    db: AsyncSession,
    kafka_producer,
) -> None:
    docs = (
        await db.execute(
            select(KycDocument).where(
                KycDocument.merchant_id == merchant_id,
                KycDocument.is_deleted.is_(False),
            )
        )
    ).scalars().all()

    verified_types = {d.document_type for d in docs if d.status == KycDocumentStatus.VERIFIED}
    if all(req in verified_types for req in REQUIRED_DOCS):
        merchant = await db.get(Merchant, merchant_id)
        if merchant and merchant.status == MerchantStatus.PENDING_KYC:
            merchant.status = MerchantStatus.ACTIVE
            await db.flush()
            if kafka_producer:
                try:
                    await kafka_producer.publish(
                        Topics.MERCHANT_KYC_COMPLETED,
                        "merchant.kyc_completed",
                        {"merchant_id": str(merchant_id)},
                        key=str(merchant_id),
                    )
                except Exception as exc:
                    log.warning("kafka.kyc_completed.failed", error=str(exc))


async def _auto_approve_dev(
    document_id: uuid.UUID,
    db: AsyncSession,
    kafka_producer,
) -> None:
    await asyncio.sleep(3)
    try:
        await approve_document(document_id, uuid.UUID(int=0), db, kafka_producer)
        log.info("kyc.auto_approved_dev", document_id=str(document_id))
    except Exception as exc:
        log.warning("kyc.auto_approve_dev.failed", error=str(exc))


async def _upload_to_s3(
    s3_client,
    bucket: str,
    key: str,
    body: bytes,
    content_type: str,
) -> None:
    if s3_client is None:
        log.info("s3.upload.skipped_no_client", key=key)
        return
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        ),
    )


def _ext_from_content_type(ct: str) -> str:
    mapping = {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
    }
    return mapping.get(ct, ".bin")
