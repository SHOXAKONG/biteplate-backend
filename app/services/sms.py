"""Eskiz.uz SMS gateway client. Stubs sends when not configured."""
import threading
import time

import httpx
import structlog

from app.config import settings

log = structlog.get_logger()


class EskizClient:
    TOKEN_TTL_SECONDS = 25 * 24 * 3600

    def __init__(self):
        self._token: str | None = None
        self._token_acquired_at: float = 0.0
        self._lock = threading.Lock()

    def send(self, to: str, body: str) -> dict:
        if not self._is_configured():
            log.info("sms_stub_send", to=to, body=body)
            return {"status": "stubbed", "to": to}

        phone = _normalize_phone(to)
        token = self._ensure_token()
        try:
            return self._post_message(phone, body, token)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                token = self._ensure_token(force_refresh=True)
                return self._post_message(phone, body, token)
            log.error("eskiz_send_failed", status=e.response.status_code, body=e.response.text)
            raise

    def _is_configured(self) -> bool:
        return bool(settings.ESKIZ_EMAIL and settings.ESKIZ_PASSWORD)

    def _ensure_token(self, force_refresh: bool = False) -> str:
        with self._lock:
            fresh = (
                self._token
                and not force_refresh
                and time.time() - self._token_acquired_at < self.TOKEN_TTL_SECONDS
            )
            if fresh:
                return self._token  # type: ignore[return-value]
            self._token = self._login()
            self._token_acquired_at = time.time()
            return self._token

    def _login(self) -> str:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"{settings.ESKIZ_BASE_URL}/auth/login",
                data={
                    "email": settings.ESKIZ_EMAIL,
                    "password": settings.ESKIZ_PASSWORD,
                },
            )
            resp.raise_for_status()
            token = resp.json()["data"]["token"]
            log.info("eskiz_token_acquired")
            return token

    def _post_message(self, phone: str, body: str, token: str) -> dict:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"{settings.ESKIZ_BASE_URL}/message/sms/send",
                headers={"Authorization": f"Bearer {token}"},
                data={
                    "mobile_phone": phone,
                    "message": body,
                    "from": settings.ESKIZ_FROM,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            log.info("sms_sent", to=phone, status=payload.get("status"), id=payload.get("id"))
            return payload


def _normalize_phone(phone: str) -> str:
    return "".join(c for c in phone if c.isdigit())


sms_client = EskizClient()
