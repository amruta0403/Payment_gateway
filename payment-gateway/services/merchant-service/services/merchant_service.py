from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.kyc_document import KycDocument
from models.merchant import DEFAULT_FEE_CONFIG, Merchant
from models.merchant_bank_account import MerchantBankAccount
from schemas.merchant import MerchantResponse, OnboardingChecklist
from shared.exceptions.handlers import PaymentGatewayError
from shared.kafka.topics import Topics
from shared.models.enums import KycDocumentStatus, MerchantStatus
from shared.utils.encryption import FieldEncryptor

log = structlog.get_logger()


class MerchantInactiveError(PaymentGatewayError):
    http_status = 400
    code = "MERCHANT_NOT_FOUND"
    message = "Merchant not found"


async def build_checklist(merchant_id: uuid.UUID, db: AsyncSession) -> OnboardingChecklist:
    m = await db.get(Merchant, merchant_id)
    if not m:
        return OnboardingChecklist()

    bank_accts = (
        await db.execute(
            select(MerchantBankAccount).where(
                MerchantBankAccount.merchant_id == merchant_id,
                MerchantBankAccount.is_deleted.is_(False),
            )
        )
    ).scalars().all()

    kyc_docs = (
        await db.execute(
            select(KycDocument).where(
                KycDocument.merchant_id == merchant_id,
                KycDocument.is_deleted.is_(False),
            )
        )
    ).scalars().all()

    verified_types = {d.document_type for d in kyc_docs if d.status == KycDocumentStatus.VERIFIED}

    from shared.models.enums import KycDocumentType
    return OnboardingChecklist(
        pan_verified=bool(m.pan_hash),
        gstin_verified=bool(m.gstin_hash),
        bank_account_added=len(bank_accts) > 0,
        bank_verified=any(a.is_verified for a in bank_accts),
        kyc_docs_uploaded=len(kyc_docs) > 0,
        kyc_approved=m.status == MerchantStatus.ACTIVE,
    )


def _merchant_to_response(
    m: Merchant,
    checklist: OnboardingChecklist,
    encryptor: FieldEncryptor,
) -> MerchantResponse:
    def safe_decrypt(value: str | None) -> str | None:
        if not value:
            return None
        try:
            return encryptor.decrypt(value)
        except Exception:
            return None

    from shared.utils.masking import mask_email, mask_phone
    email = safe_decrypt(m.support_email)
    phone = safe_decrypt(m.support_phone)

    return MerchantResponse(
        id=m.id,
        business_name=safe_decrypt(m.business_name) or "",
        business_type=m.business_type,
        status=m.status,
        website_url=m.website_url,
        support_email=mask_email(email) if email else None,
        support_phone=mask_phone(phone) if phone else None,
        business_category=m.business_category,
        fee_config=m.fee_config or DEFAULT_FEE_CONFIG,
        keycloak_group_id=m.keycloak_group_id,
        display_name=m.display_name,
        logo_url=m.logo_url,
        onboarding_checklist=checklist,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


async def create_merchant(
    request,
    registering_user_id: str,
    db: AsyncSession,
    encryptor: FieldEncryptor,
    keycloak_url: str,
    keycloak_realm: str,
    keycloak_admin_token: str,
    kafka_producer,
    environment: str = "development",
) -> MerchantResponse:
    from shared.utils.encryption import FieldEncryptor

    # ── 1 & 2. Validation already done by Pydantic ────────────────────────────

    # ── 3. Encrypt sensitive fields ───────────────────────────────────────────
    business_name_enc = encryptor.encrypt(request.business_name)
    pan_enc = encryptor.encrypt(request.pan)
    gstin_enc = encryptor.encrypt(request.gstin) if request.gstin else None
    email_enc = encryptor.encrypt(str(request.support_email))
    phone_enc = encryptor.encrypt(request.support_phone)

    # ── 4. Hash for search ────────────────────────────────────────────────────
    bname_hash = FieldEncryptor.hash_field(request.business_name.lower())
    pan_hash = FieldEncryptor.hash_field(request.pan)
    gstin_hash = FieldEncryptor.hash_field(request.gstin) if request.gstin else None

    # ── 5. Insert merchant ────────────────────────────────────────────────────
    merchant = Merchant(
        business_name=business_name_enc,
        business_name_hash=bname_hash,
        pan=pan_enc,
        pan_hash=pan_hash,
        gstin=gstin_enc,
        gstin_hash=gstin_hash,
        support_email=email_enc,
        support_phone=phone_enc,
        business_type=request.business_type,
        status=MerchantStatus.DRAFT,
        website_url=str(request.website_url) if request.website_url else None,
        support_phone=phone_enc,
        business_category=request.business_category,
        fee_config=dict(DEFAULT_FEE_CONFIG),
    )
    db.add(merchant)
    await db.flush()  # get ID

    # ── 6 & 7 & 8. Keycloak group ──────────────────────────────────────────────
    group_id = await _create_keycloak_group(
        merchant.id,
        registering_user_id,
        keycloak_url,
        keycloak_realm,
        keycloak_admin_token,
        environment,
    )
    if group_id:
        merchant.keycloak_group_id = group_id
        await db.flush()

    # ── 9. Publish Kafka event ────────────────────────────────────────────────
    if kafka_producer:
        try:
            await kafka_producer.publish(
                Topics.MERCHANT_REGISTERED,
                "merchant.registered",
                {
                    "merchant_id": str(merchant.id),
                    "business_type": merchant.business_type.value,
                    "status": merchant.status.value,
                },
                key=str(merchant.id),
            )
        except Exception as exc:
            log.warning("kafka.merchant_registered.failed", error=str(exc))

    await db.commit()

    checklist = await build_checklist(merchant.id, db)
    return _merchant_to_response(merchant, checklist, encryptor)


async def _create_keycloak_group(
    merchant_id: uuid.UUID,
    user_id: str,
    keycloak_url: str,
    realm: str,
    admin_token: str,
    environment: str,
) -> str | None:
    """Create a Keycloak group for the merchant and assign the user as MERCHANT_OWNER."""
    if environment == "development" or not admin_token:
        log.info("keycloak.group_create.skipped_dev", merchant_id=str(merchant_id))
        return f"dev-group-{merchant_id}"

    group_name = f"merchant_{merchant_id}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Create group
            resp = await client.post(
                f"{keycloak_url}/admin/realms/{realm}/groups",
                headers={
                    "Authorization": f"Bearer {admin_token}",
                    "Content-Type": "application/json",
                },
                json={"name": group_name, "attributes": {"merchant_id": [str(merchant_id)]}},
            )
            if resp.status_code not in (201, 409):
                log.warning("keycloak.group_create.failed", status=resp.status_code)
                return None

            group_id = resp.headers.get("Location", "").split("/")[-1]

            # Add user to group
            await client.put(
                f"{keycloak_url}/admin/realms/{realm}/users/{user_id}/groups/{group_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

            return group_id
    except Exception as exc:
        log.warning("keycloak.group_create.error", error=str(exc))
        return None
