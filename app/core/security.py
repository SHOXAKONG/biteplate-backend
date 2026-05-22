import time
from dataclasses import dataclass, field

import httpx
from jose import jwt
from jose.exceptions import JWTError

from app.config import settings
from app.core.exceptions import AuthError

_JWKS_CACHE: dict = {"keys": None, "fetched_at": 0.0}
_JWKS_TTL_SECONDS = 3600


@dataclass
class KeycloakUser:
    sub: str
    username: str
    email: str | None
    roles: list[str] = field(default_factory=list)
    raw_token: dict = field(default_factory=dict)


async def _fetch_jwks() -> dict:
    now = time.time()
    if _JWKS_CACHE["keys"] and now - _JWKS_CACHE["fetched_at"] < _JWKS_TTL_SECONDS:
        return _JWKS_CACHE["keys"]

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(settings.keycloak_jwks_url)
        resp.raise_for_status()
        keys = resp.json()

    _JWKS_CACHE["keys"] = keys
    _JWKS_CACHE["fetched_at"] = now
    return keys


def _extract_roles(claims: dict) -> list[str]:
    roles: list[str] = []
    realm_access = claims.get("realm_access") or {}
    roles.extend(realm_access.get("roles", []))
    resource_access = claims.get("resource_access") or {}
    client_block = resource_access.get(settings.KEYCLOAK_CLIENT_ID) or {}
    roles.extend(client_block.get("roles", []))
    return roles


async def verify_token(token: str) -> KeycloakUser:
    try:
        jwks = await _fetch_jwks()
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if key is None:
            raise AuthError("Signing key not found")

        claims = jwt.decode(
            token,
            key,
            algorithms=[key.get("alg", "RS256")],
            audience=settings.KEYCLOAK_AUDIENCE,
            options={"verify_aud": True, "verify_iss": False},
        )
        # Manual issuer check — accept either the public URL or the internal one
        # (same Keycloak instance, different network paths into it).
        token_iss = claims.get("iss", "")
        if token_iss not in settings.keycloak_acceptable_issuers:
            raise AuthError(
                f"Invalid issuer: {token_iss!r} not in "
                f"{sorted(settings.keycloak_acceptable_issuers)}"
            )
    except JWTError as e:
        raise AuthError(f"Invalid token: {e}") from e
    except httpx.HTTPError as e:
        raise AuthError(f"Could not reach Keycloak: {e}") from e

    return KeycloakUser(
        sub=claims["sub"],
        username=claims.get("preferred_username", claims["sub"]),
        email=claims.get("email"),
        roles=_extract_roles(claims),
        raw_token=claims,
    )
