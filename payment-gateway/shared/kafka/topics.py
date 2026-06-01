class Topics:
    # Payment lifecycle
    PAYMENT_INITIATED = "payment.initiated"
    PAYMENT_AUTHORIZED = "payment.authorized"
    PAYMENT_CAPTURED = "payment.captured"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_CANCELLED = "payment.cancelled"

    # Refund lifecycle
    REFUND_INITIATED = "refund.initiated"
    REFUND_PROCESSING = "refund.processing"
    REFUND_COMPLETED = "refund.completed"
    REFUND_FAILED = "refund.failed"

    # UPI events
    UPI_COLLECT_INITIATED = "upi.collect_initiated"
    UPI_CALLBACK_RECEIVED = "upi.callback_received"
    UPI_STATUS_UPDATED = "upi.status_updated"

    # Merchant / KYC
    MERCHANT_REGISTERED = "merchant.registered"
    MERCHANT_KYC_DOC_UPLOADED = "merchant.kyc_doc_uploaded"
    MERCHANT_KYC_COMPLETED = "merchant.kyc_completed"
    MERCHANT_KYC_REJECTED = "merchant.kyc_rejected"

    # Settlement
    SETTLEMENT_BATCH_CREATED = "settlement.batch_created"
    SETTLEMENT_PAYOUT_INITIATED = "settlement.payout_initiated"
    SETTLEMENT_COMPLETED = "settlement.completed"
    SETTLEMENT_FAILED = "settlement.failed"

    # Audit
    AUDIT_EVENTS = "audit.events"

    # Dead-letter queues
    DLQ_PAYMENT_EVENTS = "dlq.payment_events"
    DLQ_MERCHANT_EVENTS = "dlq.merchant_events"

    @classmethod
    def all_topics(cls) -> list[str]:
        return [
            v for k, v in vars(cls).items()
            if not k.startswith("_") and isinstance(v, str) and not callable(v)
        ]
