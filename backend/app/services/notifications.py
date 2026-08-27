"""Best-effort webhook fan-out for incident lifecycle events.

Slack incoming webhooks accept a plain `{"text": "..."}` JSON body, so one
generic webhook dispatcher covers Slack and any other consumer that reads
either the `text` field or the full JSON payload -- no Slack-specific code
path needed. See docs/agents.md#notifications.

Failures here are logged and swallowed, never raised: a notification
provider being down must never break the incident response flow itself.
"""

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def notify(event: str, incident_id: str, title: str, detail: str) -> None:
    settings = get_settings()
    urls = settings.notification_webhook_url_list
    if not urls:
        return

    payload = {
        "text": f"*[{event}]* {title}\n{detail}\n_incident {incident_id}_",
        "event": event,
        "incident_id": incident_id,
        "title": title,
        "detail": detail,
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        for url in urls:
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
            except httpx.HTTPError:
                logger.warning("Notification webhook failed (event=%s, url=%s)", event, url, exc_info=True)
