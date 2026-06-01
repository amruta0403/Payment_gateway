from __future__ import annotations

import time
from typing import Annotated, Any, Union

import httpx
import structlog
from fastapi import Depends, Header, Request
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwt
from pydantic import BaseModel

from shared.exceptions.handlers import ForbiddenError, UnauthorizedError

log = structlog.get_logger()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


class TokenPayload(BaseModel):
    sub: str
    email: str
    roles: list[str] = []
    merchant_id: str | None = None
    exp: int
    jti: str


class ApiKeyPrincipal(BaseModel):
    merchant_id: str
    permissions: list[str] = []
    environment: str = "SANDBOX"
    auth_type: str = "api_key"


# Either a Keycloak JWT payload or an API-key context
Principal = Union[TokenPayload, ApiKeyPrincipal]


class KeycloakConfig(BaseModel):
    url: str
    realm: str
    client_id: str
    client_secret: str
    jwks_cache_ttl: int = 3600


class KeycloakTokenValidator:
    def __init__(self, config: KeycloakConfig) -> None:
        self._config = config
        self._jwks_cache: dict[str, Any] | None = None
        self._jwks_fetched_at: float = 0

    @property
    def _issuer(self) -> str:
        return f"{self._config.url}/realms/{self._config.realm}"

    @property
    def _jwks_url(self) -> str:
        return f"{self._issuer}/protocol/openid-connect/certs"

    async def get_jwks(self) -> dict[str, Any]:
        now = time.monotonic()
        if (
            self._jwks_cache is not None
            and (now - self._jwks_fetched_at) < self._config.jwks_cache_ttl
        ):
            return self._jwks_cache
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(self._jwks_url)
            resp.raise_for_status()
            self._jwks_cache = resp.json()
            self._jwks_fetched_at = now
            return self._jwks_cache

    async def validate_token(self, token: str) -> TokenPayload:
        try:
            header = jwt.get_unverified_header(token)
        except JWTError as exc:
            raise UnauthorizedError("Invalid token format") from exc

        kid = header.get("kid")
        jwks = await self.get_jwks()
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if not key:
            # Stale cache — force refresh once
            self._jwks_cache = None
            jwks = await self.get_jwks()
            key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if not key:
            raise UnauthorizedError("Unknown signing key")

        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self._config.client_id,
                issuer=self._issuer,
                options={"verify_at_hash": False},
            )
        except ExpiredSignatureError as exc:
            raise UnauthorizedError("Token has expired") from exc
        except JWTError as exc:
            raise UnauthorizedError(f"Token validation failed: {exc}") from exc

        roles: list[str] = []
        realm_access = payload.get("realm_access", {})
        roles.extend(realm_access.get("roles", []))
        resource_access = payload.get("resource_access", {})
        client_roles = resource_access.get(self._config.client_id, {}).get("roles", [])
        roles.extend(client_roles)

        token_payload = TokenPayload(
            sub=payload["sub"],
            email=payload.get("email", ""),
            roles=roles,
            merchant_id=payload.get("merchant_id"),
            exp=payload["exp"],
            jti=payload.get("jti", ""),
        )

        # Check revocation in Redis (non-blocking — fail open on Redis error)
        try:
            redis = getattr(
                __import__("__main__", fromlist=["app"]).app.state, "redis", None
            )
            if redis:
                await verify_not_revoked(token_payload.jti, redis)
        except UnauthorizedError:
            raise
        except Exception:
            pass

        return token_payload

    def get_current_user_dependency(self):
        """FastAPI Depends factory → TokenPayload (JWT only)."""
        validator = self

        async def _get_current_user(
            token: Annotated[str | None, Depends(oauth2_scheme)],
        ) -> TokenPayload:
            if not token:
                raise UnauthorizedError("Bearer token required")
            return await validator.validate_token(token)

        return _get_current_user

    def get_combined_auth_dependency(self):
        """
        FastAPI Depends factory → Principal.

        Tries Bearer JWT first; falls back to x-api-key header.
        Raises 401 if neither is provided or both are invalid.
        """
        validator = self

        async def _combined_auth(
            request: Request,
            authorization: Annotated[str | None, Header(alias="authorization")] = None,
            x_api_key: Annotated[str | None, Header(alias="x-api-key")] = None,
        ) -> Principal:
            # 1. Try Bearer JWT
            if authorization and authorization.lower().startswith("bearer "):
                token = authorization[7:]
                principal = await validator.validate_token(token)
                # Stamp merchant_id onto request.state for IdempotencyMiddleware
                if principal.merchant_id:
                    request.state.merchant_id = principal.merchant_id
                return principal

            # 2. Fall back to API key
            if x_api_key:
                from shared.auth.api_key import validate_api_key

                factory = request.app.state.session_factory
                async with factory() as session:
                    api_ctx = await validate_api_key(x_api_key, session)
                request.state.merchant_id = api_ctx.merchant_id
                return ApiKeyPrincipal(
                    merchant_id=api_ctx.merchant_id,
                    permissions=api_ctx.permissions,
                    environment=api_ctx.environment,
                )

            raise UnauthorizedError("Authentication required: provide Bearer token or x-api-key")

        return _combined_auth

    def require_roles(self, *roles: str):
        """FastAPI Depends factory that checks JWT roles."""
        get_user = self.get_current_user_dependency()

        async def _check_roles(
            current_user: Annotated[TokenPayload, Depends(get_user)],
        ) -> TokenPayload:
            for role in roles:
                if role not in current_user.roles:
                    raise ForbiddenError(
                        f"Role '{role}' required. User has: {current_user.roles}"
                    )
            return current_user

        return _check_roles


async def verify_not_revoked(jti: str, redis: Any) -> None:
    from shared.cache.redis_client import is_token_revoked

    if await is_token_revoked(redis, jti):
        raise UnauthorizedError("Token has been revoked")


def build_validator_from_settings(settings: Any) -> KeycloakTokenValidator:
    """Convenience: build a KeycloakTokenValidator from a pydantic-settings object."""
    return KeycloakTokenValidator(
        KeycloakConfig(
            url=settings.KEYCLOAK_URL,
            realm=settings.KEYCLOAK_REALM,
            client_id=settings.KEYCLOAK_CLIENT_ID,
            client_secret=settings.KEYCLOAK_CLIENT_SECRET,
        )
    )
