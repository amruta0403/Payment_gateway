from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from models.kyc_document import KycDocument
from schemas.merchant import KycDocumentResponse, KycRejectRequest
from services.kyc_service import approve_document, reject_document, upload_document
from shared.models.enums import KycDocumentType

log = structlog.get_logger()
router = APIRouter(tags=["kyc"])


def _check_access(merchant_id: uuid.UUID, principal) -> None:
    roles = getattr(principal, "roles", [])
    if "ADMIN" in roles or "COMPLIANCE_OFFICER" in roles:
        return
    mid = getattr(principal, "merchant_id", None)
    if mid is None or str(mid) != str(merchant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _require_roles(principal, *roles: str) -> None:
    proles = getattr(principal, "roles", [])
    if not any(r in proles for r in roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.post(
    "/merchants/{merchant_id}/kyc/documents",
    response_model=KycDocumentResponse,
    status_code=201,
)
async def upload_kyc_document(
    merchant_id: uuid.UUID,
    request: Request,
    document_type: KycDocumentType = Form(...),
    file: UploadFile = File(...),
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    state = request.app.state
    doc = await upload_document(
        merchant_id=merchant_id,
        document_type=document_type,
        file=file,
        db=db,
        s3_client=getattr(state, "s3_client", None),
        s3_bucket=state.settings.S3_KYC_BUCKET,
        encryptor=state.encryptor,
        kafka_producer=getattr(state, "kafka_producer", None),
        environment=state.settings.ENVIRONMENT,
    )
    return KycDocumentResponse.model_validate(doc)


@router.get(
    "/merchants/{merchant_id}/kyc/documents",
    response_model=list[KycDocumentResponse],
)
async def list_kyc_documents(
    merchant_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    rows = (
        await db.execute(
            select(KycDocument).where(
                KycDocument.merchant_id == merchant_id,
                KycDocument.is_deleted.is_(False),
            )
        )
    ).scalars().all()
    return [KycDocumentResponse.model_validate(r) for r in rows]


@router.post("/admin/kyc/{doc_id}/approve", response_model=KycDocumentResponse)
async def approve_kyc_document(
    doc_id: uuid.UUID,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _require_roles(principal, "ADMIN", "COMPLIANCE_OFFICER")
    admin_id = uuid.UUID(str(getattr(principal, "sub", str(uuid.uuid4()))))
    doc = await approve_document(
        document_id=doc_id,
        admin_user_id=admin_id,
        db=db,
        kafka_producer=getattr(request.app.state, "kafka_producer", None),
    )
    return KycDocumentResponse.model_validate(doc)


@router.post("/admin/kyc/{doc_id}/reject", response_model=KycDocumentResponse)
async def reject_kyc_document(
    doc_id: uuid.UUID,
    body: KycRejectRequest,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _require_roles(principal, "ADMIN", "COMPLIANCE_OFFICER")
    admin_id = uuid.UUID(str(getattr(principal, "sub", str(uuid.uuid4()))))
    doc = await reject_document(
        document_id=doc_id,
        admin_user_id=admin_id,
        rejection_reason=body.rejection_reason,
        db=db,
    )
    return KycDocumentResponse.model_validate(doc)
