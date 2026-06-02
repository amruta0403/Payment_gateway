"""
Fee calculator — ALL arithmetic in integer paise.
Decimal is used ONLY for the percentage multiplication, then immediately
converted to int via ROUND_HALF_UP.  No float ever touches a monetary value.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class FeeBreakdown:
    gross: int      # original transaction amount in paise
    fee_paise: int  # platform MDR / flat fee
    gst_paise: int  # 18% GST on fee
    net_paise: int  # amount merchant receives

    def __post_init__(self) -> None:
        assert self.gross == self.fee_paise + self.gst_paise + self.net_paise, (
            f"Fee components must sum to gross: "
            f"{self.fee_paise}+{self.gst_paise}+{self.net_paise}"
            f"!={self.gross}"
        )
        assert self.net_paise >= 0, "Net paise cannot be negative"


# Constants
_UPI_MDR_EXEMPT_THRESHOLD_PAISE = 200_000  # ₹2,000 — RBI P2M zero-MDR mandate


def calculate_fee(
    amount_paise: int,
    payment_method: str,
    fee_config: dict,
) -> FeeBreakdown:
    """
    Calculate fee breakdown for a single transaction.

    Args:
        amount_paise:   Transaction amount in integer paise.
        payment_method: "CARD" | "UPI" | "NETBANKING" (case-insensitive).
        fee_config:     Merchant fee config dict from merchants.fee_config column.

    Returns:
        FeeBreakdown with gross, fee_paise, gst_paise, net_paise all in int paise.

    Raises:
        AssertionError if the fee components don't sum correctly.
    """
    method = payment_method.upper()

    if method == "CARD":
        mdr_pct = Decimal(str(fee_config.get("card_mdr_percent", "2.0")))
        fee = int(
            (Decimal(amount_paise) * mdr_pct / 100)
            .to_integral_value(ROUND_HALF_UP)
        )

    elif method == "UPI":
        # RBI mandate: zero MDR for P2M transactions ≤ ₹2,000
        if amount_paise <= _UPI_MDR_EXEMPT_THRESHOLD_PAISE:
            fee = 0
        else:
            fee = int(fee_config.get("upi_flat_fee_paise", 0))

    elif method == "NETBANKING":
        fee = int(fee_config.get("netbanking_flat_fee_paise", 1000))

    else:
        # Unknown method — no fee (fail-open)
        fee = 0

    gst_pct = Decimal(str(fee_config.get("gst_percent", "18")))
    gst = int(
        (Decimal(fee) * gst_pct / 100)
        .to_integral_value(ROUND_HALF_UP)
    )
    net = amount_paise - fee - gst

    return FeeBreakdown(
        gross=amount_paise,
        fee_paise=fee,
        gst_paise=gst,
        net_paise=net,
    )
