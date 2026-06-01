from __future__ import annotations

import calendar
from datetime import date

from shared.models.enums import CardCategory, CardNetwork


def luhn_check(pan: str) -> bool:
    """Standard Luhn algorithm. Returns True if the PAN passes."""
    digits = pan.strip()
    if not digits.isdigit():
        return False
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def detect_network(pan: str) -> CardNetwork:
    """
    Detect card network from PAN prefix rules.
    Covers Visa, Mastercard, Amex, RuPay, Discover.
    """
    if not pan or not pan.isdigit():
        return CardNetwork.UNKNOWN

    # Amex: 34 or 37
    if pan[:2] in ("34", "37"):
        return CardNetwork.AMEX

    # Visa: starts with 4
    if pan.startswith("4"):
        return CardNetwork.VISA

    # Need at least 4 digits for further checks
    if len(pan) < 4:
        return CardNetwork.UNKNOWN

    first2 = int(pan[:2])
    first4 = int(pan[:4])
    first6 = int(pan[:6]) if len(pan) >= 6 else 0

    # Mastercard: 51–55 or 2221–2720
    if 51 <= first2 <= 55:
        return CardNetwork.MASTERCARD
    if 2221 <= first4 <= 2720:
        return CardNetwork.MASTERCARD

    # RuPay (Indian domestic):
    # 60, 6521, 6522, 652401-652402, 6524, 6525, 817xxx
    if pan.startswith("817"):
        return CardNetwork.RUPAY
    if pan.startswith("60") and not pan.startswith("6011"):
        return CardNetwork.RUPAY
    if pan[:4] in ("6521", "6522"):
        return CardNetwork.RUPAY
    if len(pan) >= 6 and pan[:6] in ("652401", "652402", "652403", "652404", "652405"):
        return CardNetwork.RUPAY
    if pan[:4] in ("6524", "6525"):
        return CardNetwork.RUPAY

    # Discover: 6011, 622126–622925, 644–649, 65
    if pan.startswith("6011"):
        return CardNetwork.DISCOVER
    if pan.startswith("65"):
        return CardNetwork.DISCOVER
    if len(pan) >= 6 and 622126 <= first6 <= 622925:
        return CardNetwork.DISCOVER
    if len(pan) >= 3 and 644 <= int(pan[:3]) <= 649:
        return CardNetwork.DISCOVER

    # Diners Club: 300–305, 36, 38
    if pan[:3] in ("300", "301", "302", "303", "304", "305"):
        return CardNetwork.DINERS
    if pan[:2] in ("36", "38"):
        return CardNetwork.DINERS

    return CardNetwork.UNKNOWN


async def detect_category(first6: str, db) -> CardCategory:
    """
    Look up card category from BIN database.
    Falls back to UNKNOWN if BIN not found.
    """
    from sqlalchemy import select
    from models.card_token import BinDatabase

    try:
        result = await db.execute(
            select(BinDatabase).where(BinDatabase.bin == first6).limit(1)
        )
        row = result.scalar_one_or_none()
        if row and row.card_category:
            return CardCategory(row.card_category)
    except Exception:
        pass
    return CardCategory.UNKNOWN


async def get_bin_info(first6: str, db) -> dict:
    """Return issuer_bank, issuer_country, is_domestic from BIN table."""
    from sqlalchemy import select
    from models.card_token import BinDatabase

    try:
        result = await db.execute(
            select(BinDatabase).where(BinDatabase.bin == first6).limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            return {
                "issuer_bank": row.issuer_bank,
                "issuer_country": row.issuer_country,
                "is_domestic": row.is_domestic,
                "card_category": row.card_category,
            }
    except Exception:
        pass
    return {"issuer_bank": None, "issuer_country": None, "is_domestic": True, "card_category": None}


def is_card_expired(month: int, year: int) -> bool:
    """
    Returns True if the card's expiry date has passed.
    A card expires at the end of its expiry month.
    """
    today = date.today()
    last_day = calendar.monthrange(year, month)[1]
    expiry_end = date(year, month, last_day)
    return today > expiry_end
