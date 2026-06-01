from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class PaymentGatewayError(Exception):
    http_status: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "An internal error occurred"

    def __init__(
        self,
        message: str | None = None,
        param: str | None = None,
        details: Any = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.param = param
        self.details = details
        super().__init__(self.message)


class CardDeclinedError(PaymentGatewayError):
    http_status = 402
    code = "CARD_DECLINED"
    message = "Card was declined by the issuer"


class FraudBlockedError(PaymentGatewayError):
    http_status = 402
    code = "FRAUD_BLOCKED"
    message = "Transaction blocked due to fraud risk"


class DuplicateRequestError(PaymentGatewayError):
    http_status = 409
    code = "DUPLICATE_REQUEST"
    message = "Duplicate idempotency key"


class MerchantInactiveError(PaymentGatewayError):
    http_status = 403
    code = "MERCHANT_INACTIVE"
    message = "Merchant account is not active"


class InsufficientFundsError(PaymentGatewayError):
    http_status = 402
    code = "INSUFFICIENT_FUNDS"
    message = "Insufficient funds in the account"


class InvalidCardError(PaymentGatewayError):
    http_status = 400
    code = "INVALID_CARD"
    message = "Card details are invalid"


class UpiDeclinedError(PaymentGatewayError):
    http_status = 402
    code = "UPI_DECLINED"
    message = "UPI transaction was declined"


class SettlementFailedError(PaymentGatewayError):
    http_status = 500
    code = "SETTLEMENT_FAILED"
    message = "Settlement processing failed"


class TokenNotFoundError(PaymentGatewayError):
    http_status = 404
    code = "TOKEN_NOT_FOUND"
    message = "Card token not found"


class UnauthorizedError(PaymentGatewayError):
    http_status = 401
    code = "UNAUTHORIZED"
    message = "Authentication required"


class ForbiddenError(PaymentGatewayError):
    http_status = 403
    code = "FORBIDDEN"
    message = "Insufficient permissions"


class InvalidTransitionError(PaymentGatewayError):
    http_status = 400
    code = "INVALID_STATE_TRANSITION"
    message = "Invalid payment state transition"


class ServiceUnavailableError(PaymentGatewayError):
    http_status = 503
    code = "SERVICE_UNAVAILABLE"
    message = "Downstream service is unavailable"


def _error_response(exc: PaymentGatewayError, request: Request) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "param": getattr(exc, "param", None),
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(PaymentGatewayError)
    async def payment_gateway_error_handler(
        request: Request, exc: PaymentGatewayError
    ) -> JSONResponse:
        return _error_response(exc, request)

    @app.exception_handler(CardDeclinedError)
    async def card_declined_handler(request: Request, exc: CardDeclinedError) -> JSONResponse:
        return _error_response(exc, request)

    @app.exception_handler(FraudBlockedError)
    async def fraud_blocked_handler(request: Request, exc: FraudBlockedError) -> JSONResponse:
        return _error_response(exc, request)

    @app.exception_handler(DuplicateRequestError)
    async def duplicate_request_handler(
        request: Request, exc: DuplicateRequestError
    ) -> JSONResponse:
        return _error_response(exc, request)

    @app.exception_handler(UnauthorizedError)
    async def unauthorized_handler(request: Request, exc: UnauthorizedError) -> JSONResponse:
        return _error_response(exc, request)

    @app.exception_handler(ForbiddenError)
    async def forbidden_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
        return _error_response(exc, request)
