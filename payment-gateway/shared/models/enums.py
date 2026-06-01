from enum import Enum


class MerchantStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_KYC = "PENDING_KYC"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class BusinessType(str, Enum):
    SOLE_PROPRIETORSHIP = "SOLE_PROPRIETORSHIP"
    PARTNERSHIP = "PARTNERSHIP"
    PRIVATE_LIMITED = "PRIVATE_LIMITED"
    PUBLIC_LIMITED = "PUBLIC_LIMITED"
    LLP = "LLP"
    NGO = "NGO"
    TRUST = "TRUST"
    SOCIETY = "SOCIETY"


class TransactionStatus(str, Enum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    SETTLEMENT_INITIATED = "SETTLEMENT_INITIATED"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    DISPUTED = "DISPUTED"
    CHARGEBACK = "CHARGEBACK"


class PaymentMethod(str, Enum):
    CARD = "CARD"
    UPI = "UPI"
    NETBANKING = "NETBANKING"
    WALLET = "WALLET"
    EMI = "EMI"
    BNPL = "BNPL"


class FraudDecision(str, Enum):
    ALLOW = "ALLOW"
    CHALLENGE = "CHALLENGE"
    BLOCK = "BLOCK"


class SettlementStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ON_HOLD = "ON_HOLD"


class PayoutStatus(str, Enum):
    INITIATED = "INITIATED"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REVERSED = "REVERSED"


class PayoutMethod(str, Enum):
    IMPS = "IMPS"
    NEFT = "NEFT"
    RTGS = "RTGS"
    UPI = "UPI"


class RefundStatus(str, Enum):
    INITIATED = "INITIATED"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REVERSED = "REVERSED"


class RefundSource(str, Enum):
    MERCHANT = "MERCHANT"
    CUSTOMER = "CUSTOMER"
    SYSTEM = "SYSTEM"
    CHARGEBACK = "CHARGEBACK"


class KycDocumentType(str, Enum):
    PAN = "PAN"
    AADHAR = "AADHAR"
    GSTIN = "GSTIN"
    BANK_STATEMENT = "BANK_STATEMENT"
    CERTIFICATE_OF_INCORPORATION = "CERTIFICATE_OF_INCORPORATION"
    CANCELLED_CHEQUE = "CANCELLED_CHEQUE"
    BUSINESS_ADDRESS_PROOF = "BUSINESS_ADDRESS_PROOF"


class KycDocumentStatus(str, Enum):
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class UpiStatus(str, Enum):
    INITIATED = "INITIATED"
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    REVERSED = "REVERSED"


class NotificationType(str, Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    PUSH = "PUSH"
    WEBHOOK = "WEBHOOK"


class NotificationStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"


class CardNetwork(str, Enum):
    VISA = "VISA"
    MASTERCARD = "MASTERCARD"
    AMEX = "AMEX"
    RUPAY = "RUPAY"
    DISCOVER = "DISCOVER"
    DINERS = "DINERS"
    UNKNOWN = "UNKNOWN"


class CardCategory(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    PREPAID = "PREPAID"
    CORPORATE = "CORPORATE"
    UNKNOWN = "UNKNOWN"


class Environment(str, Enum):
    LIVE = "LIVE"
    SANDBOX = "SANDBOX"
