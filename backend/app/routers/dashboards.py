import httpx
from fastapi import APIRouter, HTTPException, Response

from app.config import get_settings

router = APIRouter()


@router.get("/panel-image")
async def panel_image(dashboard_uid: str, panel_id: int, width: int = 1000, height: int = 500) -> Response:
    """Proxies a rendered dashboard panel PNG for the control room UI and postmortem.

    In the live agent crew this image is produced by the Responder/Wrap
    agents calling the Grafana MCP `get_panel_image` tool; this endpoint lets
    the frontend fetch the same panel image directly over REST without
    round-tripping through an agent turn. Both paths ultimately hit Grafana's
    own image-rendering HTTP API.
    """
    settings = get_settings()
    if not settings.grafana_url:
        raise HTTPException(501, "GRAFANA_URL is not configured")

    render_url = f"{settings.grafana_url.rstrip('/')}/render/d-solo/{dashboard_uid}"
    params = {"panelId": panel_id, "width": width, "height": height, "tz": "UTC"}
    headers = {}
    if settings.grafana_service_account_token:
        headers["Authorization"] = f"Bearer {settings.grafana_service_account_token}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(render_url, params=params, headers=headers)

    if resp.status_code != 200:
        raise HTTPException(resp.status_code, "Failed to render panel image from Grafana")

    return Response(content=resp.content, media_type="image/png")
