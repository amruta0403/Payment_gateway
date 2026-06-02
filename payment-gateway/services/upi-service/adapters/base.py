from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from models.upi_transaction import UpiStatus


@dataclass
class VpaResolution:
    is_valid: bool
    account_name: str | None = None
    bank_name: str | None = None


@dataclass
class NpciCollectRequest:
    our_ref_id: str
    payer_vpa: str
    payee_vpa: str
    amount: int          # paise
    description: str
    expiry_seconds: int = 300


@dataclass
class NpciCollectResponse:
    our_ref_id: str
    status: UpiStatus
    npci_txn_id: str | None = None
    expires_at: datetime | None = None
    decline_code: str | None = None
    decline_reason: str | None = None


@dataclass
class NpciStatusResponse:
    status: UpiStatus
    npci_txn_id: str | None = None
    completed_at: datetime | None = None
    decline_code: str | None = None
    decline_reason: str | None = None


class NpciClient(ABC):
    """Abstract interface to the NPCI / UPI network."""

    @abstractmethod
    async def resolve_vpa(self, vpa: str) -> VpaResolution: ...

    @abstractmethod
    async def send_collect(self, req: NpciCollectRequest) -> NpciCollectResponse: ...

    @abstractmethod
    async def check_status(self, our_ref_id: str) -> NpciStatusResponse: ...

    @abstractmethod
    async def validate_callback(self, headers: dict, body: bytes) -> bool: ...

    @abstractmethod
    def generate_qr(self, vpa: str, amount: int, description: str) -> str | None: ...
