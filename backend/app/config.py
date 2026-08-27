from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, sourced from environment variables / .env.

    See docs/deployment.md for the full environment variable reference.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Grafana Cloud MCP
    grafana_url: str = ""
    grafana_mcp_endpoint: str = "https://mcp.grafana.com/mcp"
    grafana_service_account_token: str = ""

    # Google ADK / Gemini. Two supported auth paths -- see docs/deployment.md:
    #   - Vertex AI (recommended for Cloud Run): google_genai_use_vertexai=True
    #     with google_cloud_project/google_cloud_location set, no API key --
    #     google-genai authenticates via the Cloud Run service account's
    #     Application Default Credentials (see infra/scripts/00-setup.sh).
    #   - Gemini Developer API: google_api_key set, used for local dev or if
    #     you'd rather not grant Vertex AI IAM roles.
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    google_genai_use_vertexai: bool = False
    google_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"

    # Persistence
    database_url: str = "sqlite+aiosqlite:///./premiere_control_room.db"

    # Demo / ops
    demo_mode: bool = True
    cors_origins: str = "*"

    # Sentinel background polling loop (only runs once agents_configured is True)
    sentinel_poll_interval_seconds: float = 15.0
    sentinel_slo_thresholds_json: str = ""  # JSON list of {metric_name, threshold, region}; see sentinel_loop.py

    # Synthetic live streaming pipeline (see app/simulate/otel_pipeline.py)
    simulate_live_pipeline: bool = True
    otel_exporter_otlp_endpoint: str = ""  # e.g. Grafana Cloud's OTLP gateway; console export if unset
    otel_tick_interval_seconds: float = 5.0
    otel_export_interval_seconds: float = 10.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def agents_configured(self) -> bool:
        """True once real Gemini + Grafana MCP credentials are present.

        Without these, the orchestrator falls back to a deterministic mock
        crew so the API and UI remain fully exercisable in local/demo runs.
        Gemini access counts as configured via either auth path: an API key,
        or Vertex AI mode with a project set (credentials then come from
        Application Default Credentials -- the Cloud Run service account in
        production, `gcloud auth application-default login` locally).
        """
        gemini_configured = bool(self.google_api_key) or bool(
            self.google_genai_use_vertexai and self.google_cloud_project
        )
        return bool(gemini_configured and self.grafana_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
