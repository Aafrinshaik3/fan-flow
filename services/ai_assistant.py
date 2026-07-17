"""
GenAI-powered stadium assistant.

Wraps the Anthropic Messages API to answer fan/staff/volunteer questions
about wayfinding, accessibility, transport, and general tournament
operations -- in whatever language the visitor writes in.

Design notes (efficiency + security):
- One short, cached system prompt (not rebuilt per request) carries all the
  static stadium knowledge, keeping each call to a single small request.
- User input is length-capped and sanitized upstream (see security.py)
  before it ever reaches this module.
- The client fails closed: any API error surfaces a safe, generic message
  to the caller rather than leaking exception internals.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from anthropic import Anthropic, APIError

from config import config

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are FanFlow, an on-site assistant at a FIFA World Cup 2026 host stadium.
You help fans, volunteers, and venue staff with:
- Wayfinding: gates, seating blocks, restrooms, food/retail, exits, transit links
- Accessibility: step-free routes, accessible seating, sensory rooms, assistive services
- Transport & logistics: shuttle times, rideshare zones, parking, last-train warnings
- Crowd & safety guidance: calmly redirecting away from congested areas
- General tournament info: schedules, bag policy, re-entry rules

Rules:
- Reply in the same language the visitor used, even if you switch mid-conversation.
- Keep answers short (2-4 sentences) and concrete -- this is read on a phone
  in a crowd, not a report.
- If you don't have specific venue data, say so plainly and suggest asking
  a steward, rather than inventing gate numbers or times.
- Never provide medical, legal, or emergency-dispatch advice; for any
  medical or safety emergency, tell the person to alert the nearest steward
  or call local emergency services immediately.
"""

_FALLBACK_MESSAGE = (
    "The AI assistant is temporarily unavailable. Please ask the nearest "
    "steward or check the venue signage for directions."
)


@dataclass
class AssistantReply:
    text: str
    degraded: bool = False


class StadiumAssistant:
    """Thin, testable wrapper around the Anthropic client."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key if api_key is not None else config.anthropic_api_key
        self._model = model or config.anthropic_model
        self._client = Anthropic(api_key=self._api_key) if self._api_key else None

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    def ask(self, message: str, history: list[dict] | None = None) -> AssistantReply:
        """
        Answer a single visitor question.

        `history` is an optional list of prior {"role", "content"} turns for
        short multi-turn conversations; kept small by the caller to bound cost.
        """
        if not self.is_configured:
            logger.warning("Assistant called without ANTHROPIC_API_KEY configured.")
            return AssistantReply(text=_FALLBACK_MESSAGE, degraded=True)

        messages = (history or []) + [{"role": "user", "content": message}]

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=300,
                system=_SYSTEM_PROMPT,
                messages=messages,
            )
        except APIError:
            logger.exception("Anthropic API call failed.")
            return AssistantReply(text=_FALLBACK_MESSAGE, degraded=True)

        text_parts = [block.text for block in response.content if block.type == "text"]
        return AssistantReply(text="".join(text_parts).strip() or _FALLBACK_MESSAGE)


# Module-level singleton, imported by the Flask app.
assistant = StadiumAssistant()
