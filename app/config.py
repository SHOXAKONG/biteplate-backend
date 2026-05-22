from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "postgresql+asyncpg://biteplate:biteplate@postgres:5432/biteplate"
    SYNC_DATABASE_URL: str = "postgresql://biteplate:biteplate@postgres:5432/biteplate"

    CELERY_BROKER_URL: str = "amqp://guest:guest@rabbitmq:5672//"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"

    KEYCLOAK_SERVER_URL: str = "http://keycloak:8080"
    KEYCLOAK_INTERNAL_URL: str = ""
    KEYCLOAK_REALM: str = "biteplate"
    KEYCLOAK_CLIENT_ID: str = "biteplate-backend"
    KEYCLOAK_AUDIENCE: str = "biteplate-backend"
    KEYCLOAK_ADMIN_USERNAME: str = ""
    KEYCLOAK_ADMIN_PASSWORD: str = ""

    LOCATION_CODE: str = "STANDARD"

    ESKIZ_BASE_URL: str = "https://notify.eskiz.uz/api"
    ESKIZ_EMAIL: str = ""
    ESKIZ_PASSWORD: str = ""
    ESKIZ_FROM: str = "4546"

    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def keycloak_issuer(self) -> str:
        return f"{self.KEYCLOAK_SERVER_URL}/realms/{self.KEYCLOAK_REALM}"

    @property
    def keycloak_acceptable_issuers(self) -> set[str]:
        """Both URLs point at the same Keycloak. Tokens minted via the backend
        proxy carry the INTERNAL_URL issuer; tokens minted via the browser carry
        the SERVER_URL issuer. Accept both."""
        out = {f"{self.KEYCLOAK_SERVER_URL}/realms/{self.KEYCLOAK_REALM}"}
        if self.KEYCLOAK_INTERNAL_URL:
            out.add(f"{self.KEYCLOAK_INTERNAL_URL}/realms/{self.KEYCLOAK_REALM}")
        return out

    @property
    def _keycloak_jwks_base(self) -> str:
        return self.KEYCLOAK_INTERNAL_URL or self.KEYCLOAK_SERVER_URL

    @property
    def keycloak_jwks_url(self) -> str:
        return f"{self._keycloak_jwks_base}/realms/{self.KEYCLOAK_REALM}/protocol/openid-connect/certs"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
