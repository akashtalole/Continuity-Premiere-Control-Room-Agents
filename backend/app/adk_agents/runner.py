"""Thin wrapper around google.adk.runners.Runner for one-shot agent turns.

The orchestrator hands each agent a JSON-encoded input payload and gets back
its structured (output_schema-validated) reply as a dict. One Runner +
in-memory session per agent is reused across incidents; each incident gets
its own session_id so agent memory never leaks across incidents.
"""

import json
import logging
from typing import Any

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

logger = logging.getLogger(__name__)

APP_NAME = "premiere-control-room"
USER_ID = "control-room"


class AgentInvoker:
    """Runs one ADK agent for a single turn and returns its structured output."""

    def __init__(self, agent: Agent) -> None:
        self._agent = agent
        self._session_service = InMemorySessionService()
        self._runner = Runner(agent=agent, app_name=APP_NAME, session_service=self._session_service)

    async def run(self, incident_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        session_id = f"{self._agent.name}-{incident_id}"
        await self._session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)

        message = types.Content(role="user", parts=[types.Part(text=json.dumps(input_data, default=str))])

        final_text: str | None = None
        async for event in self._runner.run_async(user_id=USER_ID, session_id=session_id, new_message=message):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = "".join(part.text or "" for part in event.content.parts)

        if final_text is None:
            raise RuntimeError(f"Agent '{self._agent.name}' produced no final response for incident {incident_id}")

        try:
            return json.loads(final_text)
        except json.JSONDecodeError:
            logger.warning("Agent '%s' returned non-JSON output; wrapping as raw text", self._agent.name)
            return {"raw_text": final_text}
