from decimal import ROUND_HALF_UP, Decimal

from shared.exceptions.handlers import PaymentGatewayError

_MAX_AMOUNT_PAISE = 10_00_00_000  # ₹1 crore in paise


class AmountError(PaymentGatewayError):
    http_status = 400
    code = "INVALID_AMOUNT"
    message = "Amount is invalid"


def validate_amount(amount: int) -> None:
    if amount <= 0:
        raise AmountError("Amount must be greater than zero", param="amount")
    if amount > _MAX_AMOUNT_PAISE:
        raise AmountError(
            f"Amount exceeds maximum of ₹1 crore ({_MAX_AMOUNT_PAISE} paise)",
            param="amount",
        )


def paise_to_rupees(paise: int) -> str:
    rupees = Decimal(paise) / 100
    int_part, dec_part = f"{rupees:.2f}".split(".")
    # Indian number format: last 3 digits then groups of 2
    if len(int_part) > 3:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        groups: list[str] = []
        while rest:
            groups.append(rest[-2:])
            rest = rest[:-2]
        int_formatted = ",".join(reversed(groups)) + "," + last3
    else:
        int_formatted = int_part
    return f"₹{int_formatted}.{dec_part}"


def rupees_to_paise(rupees: Decimal) -> int:
    return int((rupees * 100).to_integral_value(ROUND_HALF_UP))


def format_inr(paise: int) -> str:
    return paise_to_rupees(paise)
