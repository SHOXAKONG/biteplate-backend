"""Keycloak admin REST API client. Used to create users from the backend."""
import asyncio
import time

import httpx
import structlog

from app.config import settings
from app.core.exceptions import AuthError, BitePlateError, ConflictError

log = structlog.get_logger()


class KeycloakAdminClient:
    def __init__(self):
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        return settings.KEYCLOAK_INTERNAL_URL or settings.KEYCLOAK_SERVER_URL

    async def _get_token(self) -> str:
        async with self._lock:
            if self._token and time.time() < self._token_expires_at:
                return self._token
            if not settings.KEYCLOAK_ADMIN_USERNAME or not settings.KEYCLOAK_ADMIN_PASSWORD:
                raise BitePlateError(
                    "KEYCLOAK_ADMIN_USERNAME / KEYCLOAK_ADMIN_PASSWORD must be set to create users"
                )
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.base_url}/realms/master/protocol/openid-connect/token",
                    data={
                        "grant_type": "password",
                        "client_id": "admin-cli",
                        "username": settings.KEYCLOAK_ADMIN_USERNAME,
                        "password": settings.KEYCLOAK_ADMIN_PASSWORD,
                    },
                )
            if resp.status_code != 200:
                raise AuthError(f"Could not authenticate to Keycloak admin: {resp.text}")
            data = resp.json()
            self._token = data["access_token"]
            self._token_expires_at = time.time() + data.get("expires_in", 60) - 30
            return self._token  # pyright: ignore[reportReturnType]

    async def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        realm_roles: list[str],
    ) -> dict:
        token = await self._get_token()
        users_url = f"{self.base_url}/admin/realms/{settings.KEYCLOAK_REALM}/users"

        async with httpx.AsyncClient(timeout=10.0) as client:
            create_resp = await client.post(
                users_url,
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "username": username,
                    "email": email,
                    "firstName": first_name,
                    "lastName": last_name,
                    "enabled": True,
                    "emailVerified": True,
                    "credentials": [
                        {"type": "password", "value": password, "temporary": False}
                    ],
                },
            )

            if create_resp.status_code == 409:
                raise ConflictError(f"User '{username}' or that email already exists")
            if create_resp.status_code not in (201, 204):
                raise BitePlateError(
                    f"Keycloak user creation failed ({create_resp.status_code}): {create_resp.text}"
                )

            user_id = self._extract_user_id(create_resp.headers.get("Location", ""))
            if not user_id:
                user_id = await self._lookup_user_id(client, token, username)

            if realm_roles:
                role_objects = await self._fetch_role_objects(client, token, realm_roles)
                role_resp = await client.post(
                    f"{users_url}/{user_id}/role-mappings/realm",
                    headers={"Authorization": f"Bearer {token}"},
                    json=role_objects,
                )
                if role_resp.status_code not in (200, 204):
                    raise BitePlateError(
                        f"Role assignment failed ({role_resp.status_code}): {role_resp.text}"
                    )

        log.info("keycloak_user_created", username=username, roles=realm_roles)
        return {"id": user_id, "username": username, "email": email, "roles": realm_roles}

    async def list_users(self, role: str | None = None) -> list[dict]:
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {"max": "100"}
            resp = await client.get(
                f"{self.base_url}/admin/realms/{settings.KEYCLOAK_REALM}/users",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            resp.raise_for_status()
            users = resp.json()
            # Fetch realm-role mappings per user (one call each — fine for small realms).
            out: list[dict] = []
            for u in users:
                roles_resp = await client.get(
                    f"{self.base_url}/admin/realms/{settings.KEYCLOAK_REALM}/users/{u['id']}/role-mappings/realm",
                    headers={"Authorization": f"Bearer {token}"},
                )
                roles = (
                    [r["name"] for r in roles_resp.json()]
                    if roles_resp.status_code == 200
                    else []
                )
                if role and role not in roles:
                    continue
                out.append(
                    {
                        "id": u["id"],
                        "username": u.get("username", ""),
                        "email": u.get("email"),
                        "first_name": u.get("firstName"),
                        "last_name": u.get("lastName"),
                        "enabled": u.get("enabled", False),
                        "roles": roles,
                    }
                )
            return out

    async def set_user_enabled(self, user_id: str, enabled: bool) -> None:
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.put(
                f"{self.base_url}/admin/realms/{settings.KEYCLOAK_REALM}/users/{user_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"enabled": enabled},
            )
        if resp.status_code not in (200, 204):
            raise BitePlateError(f"Failed to update user ({resp.status_code}): {resp.text}")
        log.info("keycloak_user_enabled_changed", user_id=user_id, enabled=enabled)

    async def reset_password(self, user_id: str, new_password: str) -> None:
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.put(
                f"{self.base_url}/admin/realms/{settings.KEYCLOAK_REALM}/users/{user_id}/reset-password",
                headers={"Authorization": f"Bearer {token}"},
                json={"type": "password", "value": new_password, "temporary": False},
            )
        if resp.status_code not in (200, 204):
            raise BitePlateError(f"Password reset failed ({resp.status_code}): {resp.text}")
        log.info("keycloak_password_reset", user_id=user_id)

    @staticmethod
    def _extract_user_id(location_header: str) -> str:
        if not location_header:
            return ""
        return location_header.rsplit("/", 1)[-1]

    async def _lookup_user_id(self, client: httpx.AsyncClient, token: str, username: str) -> str:
        resp = await client.get(
            f"{self.base_url}/admin/realms/{settings.KEYCLOAK_REALM}/users",
            headers={"Authorization": f"Bearer {token}"},
            params={"username": username, "exact": "true"},
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            raise BitePlateError(f"Created user '{username}' could not be located afterwards")
        return results[0]["id"]

    async def _fetch_role_objects(
        self, client: httpx.AsyncClient, token: str, role_names: list[str]
    ) -> list[dict]:
        role_objects: list[dict] = []
        for name in role_names:
            resp = await client.get(
                f"{self.base_url}/admin/realms/{settings.KEYCLOAK_REALM}/roles/{name}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 404:
                raise BitePlateError(f"Role '{name}' does not exist in the realm")
            resp.raise_for_status()
            role_objects.append(resp.json())
        return role_objects


keycloak_admin = KeycloakAdminClient()
