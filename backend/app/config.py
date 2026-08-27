from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, sourced from environment variables / .env.

    See docs/deployment.md for the full environment variable reference.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Grafana Cloud MCP -- see docs/agents.md#grafana-mcp-tool-access for the
    # two auth paths this splits into:
    #   - Self-hosted `grafana/mcp-grafana` (infra/scripts/deploy-mcp-grafana.sh):
    #     the only option that works from an unattended Cloud Run backend. The
    #     mcp-grafana server holds grafana_service_account_token itself (its
    #     own credential for calling Grafana); this backend instead presents
    #     grafana_mcp_server_token, the separate caller-auth secret mcp-grafana
    #     was started with (--server-auth-token / MCP_GRAFANA_SERVER_TOKEN).
    #   - Hosted mcp.grafana.com: multi-tenant, routed by grafana_url via the
    #     X-Grafana-URL header, but only accepts an interactive OAuth 2.1
    #     session -- there is no service-account option, so it cannot be
    #     driven headlessly and is not what production deployments should use.
    grafana_url: str = ""
    grafana_mcp_endpoint: str = "https://mcp.grafana.com/mcp"
    grafana_service_account_token: str = ""
    grafana_mcp_server_token: str = ""

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

    # Auth -- see app/auth.py. jwt_secret left empty generates a random,
    # process-lifetime-only secret (fine for a single demo instance; tokens
    # just stop validating across a restart). Set it explicitly for anything
    # multi-instance or where sessions should survive a redeploy.
    jwt_secret: str = ""
    jwt_expiry_minutes: int = 480
    # Bootstrap admin, created once on first startup if the users table is
    # empty. If admin_password is left blank, a random one is generated and
    # logged once at WARNING level -- see app/auth.py:ensure_bootstrap_data.
    admin_email: str = "admin@premiere.local"
    admin_password: str = ""

    # Notifications -- see app/services/notifications.py. Comma-separated
    # webhook URLs (Slack incoming webhooks accept this same {"text": ...}
    # JSON shape, so no separate Slack-specific integration is needed).
    notification_webhook_urls: str = ""
    escalation_timeout_seconds: float = 300.0

    @property
    def notification_webhook_url_list(self) -> list[str]:
        return [u.strip() for u in self.notification_webhook_urls.split(",") if u.strip()]

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
