"""Login / refresh / logout — proxies to Keycloak's OIDC token endpoint."""
import httpx
import structlog

from app.config import settings
from app.core.exceptions import AuthError, BitePlateError

log = structlog.get_logger()

LOGIN_CLIENT_ID = "biteplate-frontend"


def _kc_base() -> str:
    return settings.KEYCLOAK_INTERNAL_URL or settings.KEYCLOAK_SERVER_URL


def _token_url() -> str:
    return f"{_kc_base()}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/token"


def _logout_url() -> str:
    return f"{_kc_base()}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/logout"


async def login(username: str, password: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            _token_url(),
            data={
                "grant_type": "password",
                "client_id": LOGIN_CLIENT_ID,
                "username": username,
                "password": password,
                "scope": "openid",
            },
        )
    if resp.status_code == 401:
        raise AuthError("Invalid username or password")
    if resp.status_code != 200:
        raise AuthError(f"Login failed ({resp.status_code}): {resp.text}")
    return resp.json()


async def refresh(refresh_token: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            _token_url(),
            data={
                "grant_type": "refresh_token",
                "client_id": LOGIN_CLIENT_ID,
                "refresh_token": refresh_token,
            },
        )
    if resp.status_code in (400, 401):
        raise AuthError("Refresh token invalid or expired")
    if resp.status_code != 200:
        raise BitePlateError(f"Refresh failed ({resp.status_code}): {resp.text}")
    return resp.json()


async def change_password(username: str, current_password: str, new_password: str) -> None:
    """Verify current password by attempting a login, then reset it via admin API."""
    try:
        await login(username, current_password)
    except AuthError as e:
        raise AuthError("Current password is incorrect") from e

    from app.services.keycloak_admin import keycloak_admin

    token = await keycloak_admin._get_token()  # noqa: SLF001
    async with httpx.AsyncClient(timeout=10.0) as client:
        users = await client.get(
            f"{keycloak_admin.base_url}/admin/realms/{settings.KEYCLOAK_REALM}/users",
            headers={"Authorization": f"Bearer {token}"},
            params={"username": username, "exact": "true"},
        )
        users.raise_for_status()
        results = users.json()
        if not results:
            raise BitePlateError(f"User '{username}' not found")
        user_id = results[0]["id"]

    await keycloak_admin.reset_password(user_id, new_password)
    log.info("password_changed", username=username)


async def logout(refresh_token: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            _logout_url(),
            data={
                "client_id": LOGIN_CLIENT_ID,
                "refresh_token": refresh_token,
            },
        )
    if resp.status_code not in (200, 204):
        log.warning("logout_non_success", status=resp.status_code, body=resp.text)
