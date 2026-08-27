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
        # Token usage from the most recent run() call -- see
        # orchestrator._record_token_usage. None for an invoker that hasn't
        # run yet, or one with no billable usage to report (the mock crew's
        # invokers never set this, since they never call an LLM).
        self.last_usage: dict[str, int] | None = None

    async def run(self, incident_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        session_id = f"{self._agent.name}-{incident_id}"
        await self._session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)

        message = types.Content(role="user", parts=[types.Part(text=json.dumps(input_data, default=str))])

        final_text: str | None = None
        input_tokens = 0
        output_tokens = 0
        async for event in self._runner.run_async(user_id=USER_ID, session_id=session_id, new_message=message):
            # Each yielded Event here is one complete model/tool turn (this
            # invoker doesn't use ADK's token-streaming mode), so its own
            # usage_metadata -- when present, i.e. on turns that actually
            # called the model -- is that turn's own token count, not a
            # running total to be careful not to double-count.
            usage = event.usage_metadata
            if usage is not None:
                input_tokens += usage.prompt_token_count or 0
                output_tokens += usage.candidates_token_count or 0
            if event.is_final_response() and event.content and event.content.parts:
                final_text = "".join(part.text or "" for part in event.content.parts)

        self.last_usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}

        if final_text is None:
            raise RuntimeError(f"Agent '{self._agent.name}' produced no final response for incident {incident_id}")

        try:
            return json.loads(final_text)
        except json.JSONDecodeError:
            logger.warning("Agent '%s' returned non-JSON output; wrapping as raw text", self._agent.name)
            return {"raw_text": final_text}
