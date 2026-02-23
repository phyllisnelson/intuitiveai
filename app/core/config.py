"""Application configuration via pydantic-settings.

Settings are loaded from environment variables (and an optional .env file).
All OpenStack credentials live here so they can be injected / overridden
without touching source code.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "VM Lifecycle API"
    app_version: str = "0.1.0"
    log_level: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )

    # Optional static API key.  When non-empty every request must carry
    # `X-API-Key: <value>` in the header.  Leave empty to disable (dev/PoC).
    api_key: str = ""

    openstack_auth_url: str = "https://openstack.example.internal:5000/v3"
    openstack_username: str = "api-svc"
    openstack_password: str = ""
    openstack_project_name: str = "default-project"
    openstack_project_domain_name: str = "Default"
    openstack_user_domain_name: str = "Default"
    openstack_region_name: str = "RegionOne"
    openstack_default_network_id: str = ""

    # Required. Tasks persist across restarts and are shared across workers.
    redis_url: str | None = None
    task_ttl_seconds: int = 86400  # 24 h — Redis keys expire automatically

    # Set keycloak_url to enable OIDC. Leave blank to use api_key only.
    # At least one of keycloak_url or api_key must be set.
    keycloak_url: str = ""  # e.g. https://keycloak.example.internal
    keycloak_realm: str = "vm-api"
    keycloak_client_id: str = "vm-api"
    keycloak_client_secret: str = ""
    keycloak_reader_role: str = "vm-reader"
    keycloak_operator_role: str = "vm-operator"

    @property
    def openstack_conn_kwargs(self) -> dict:
        """Return a kwargs dict suitable for ``openstack.connect(**kwargs)``."""
        return {
            "auth_url": self.openstack_auth_url,
            "username": self.openstack_username,
            "password": self.openstack_password,
            "project_name": self.openstack_project_name,
            "project_domain_name": self.openstack_project_domain_name,
            "user_domain_name": self.openstack_user_domain_name,
            "region_name": self.openstack_region_name,
        }


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — import and call this everywhere instead of
    instantiating Settings() directly."""
    return Settings()
