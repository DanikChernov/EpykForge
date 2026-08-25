from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "EPYK Forge"
    environment: str = Field(default="local", alias="FORGE_ENV")
    service_name: str = Field(default="forge-api", alias="K_SERVICE")
    cloud_run_revision: str | None = Field(default=None, alias="K_REVISION")
    google_cloud_project: str | None = Field(default=None, alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field(default="global", alias="GOOGLE_CLOUD_LOCATION")
    google_genai_use_enterprise: bool = Field(default=True, alias="GOOGLE_GENAI_USE_ENTERPRISE")

    demo_mode: bool = Field(default=True, alias="FORGE_DEMO_MODE")
    demo_speed: float = Field(default=8.0, alias="FORGE_DEMO_SPEED")
    demo_data_enabled: bool = Field(default=True, alias="FORGE_DEMO_DATA_ENABLED")
    demo_supervisor_token: str = Field(default="demo-supervisor-token", alias="FORGE_DEMO_SUPERVISOR_TOKEN")
    admin_pin: str = Field(default="1234", alias="FORGE_ADMIN_PIN")

    store_backend: str = Field(default="local", alias="FORGE_STORE_BACKEND")
    state_path: Path = Field(default=Path("./data/forge_state.json"), alias="FORGE_STATE_PATH")
    event_bus: str = Field(default="inprocess", alias="FORGE_EVENT_BUS")

    model_provider: str = Field(default="TEST_STUB", alias="FORGE_MODEL_PROVIDER")
    gemini_model: str = Field(default="gemini-3.5-flash", alias="FORGE_GEMINI_MODEL")
    model_timeout_seconds: float = Field(default=30.0, alias="FORGE_MODEL_TIMEOUT")
    max_model_calls_per_incident: int = Field(default=18, alias="FORGE_MAX_MODEL_CALLS_PER_INCIDENT")
    max_tool_calls_per_agent: int = Field(default=12, alias="FORGE_MAX_TOOL_CALLS_PER_AGENT")
    max_agent_depth: int = Field(default=6, alias="FORGE_MAX_AGENT_DEPTH")
    incident_timeout_seconds: int = Field(default=180, alias="FORGE_INCIDENT_TIMEOUT_SECONDS")

    api_cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )

    @model_validator(mode="after")
    def prevent_production_stub(self) -> Settings:
        if self.environment.lower() in {"production", "prod"} and self.model_provider != "REAL_GEMINI":
            raise ValueError("Production deployments must set FORGE_MODEL_PROVIDER=REAL_GEMINI")
        return self

    @property
    def running_on_google_cloud(self) -> bool:
        return bool(self.cloud_run_revision and self.google_cloud_project)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
