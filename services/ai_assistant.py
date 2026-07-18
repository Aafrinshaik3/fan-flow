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

import json
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

_TRIAGE_SYSTEM_PROMPT = """\
You are an operations triage assistant at a FIFA World Cup 2026 stadium.
A steward, volunteer, or staff member will describe a situation in their
own words. Classify it to help the control room route it correctly.

Respond with ONLY a JSON object, no other text, in exactly this shape:
{"category": "medical" | "security" | "crowd" | "facilities" | "lost_and_found" | "other",
 "priority": "low" | "medium" | "high" | "critical",
 "action": "<one short sentence: who to notify and what to do first>"}

Guidance:
- "critical" = immediate risk to life/safety (medical emergencies, fights,
  fire, structural issues, crush risk). These must always be routed to
  on-site emergency services first, not just stadium staff.
- "high" = urgent but not immediately life-threatening (rapidly building
  crowd surge, missing child, credible security concern).
- "medium"/"low" = standard operational issues (spill, broken turnstile,
  lost item, minor complaint).
- Never invent facts not in the report. If the description is too vague
  to classify, use category "other" and priority "low", and say so in
  the action.
"""

_TRIAGE_FALLBACK = {
    "category": "other",
    "priority": "medium",
    "action": (
        "AI triage unavailable -- escalate this report to the control room "
        "manually so a human can prioritize it."
    ),
}


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

    def triage_incident(self, description: str) -> dict:
        """
        Classify a free-text incident report into a category, priority, and
        recommended first action for the control room.

        Always returns a well-formed dict, even on API failure or malformed
        model output, so callers never have to special-case this method.
        """
        if not self.is_configured:
            logger.warning("Triage called without ANTHROPIC_API_KEY configured.")
            return dict(_TRIAGE_FALLBACK)

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=200,
                system=_TRIAGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": description}],
            )
        except APIError:
            logger.exception("Anthropic API call failed during triage.")
            return dict(_TRIAGE_FALLBACK)

        raw_text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        return parse_triage_response(raw_text)


def parse_triage_response(raw_text: str) -> dict:
    """
    Parse the model's JSON triage response defensively.

    Pulled out as a standalone function (rather than inlined) so it can be
    unit-tested against malformed/unexpected model output without needing
    a live API call.
    """
    valid_categories = {
        "medical", "security", "crowd", "facilities", "lost_and_found", "other",
    }
    valid_priorities = {"low", "medium", "high", "critical"}

    try:
        data = json.loads(raw_text.strip())
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Triage response was not valid JSON: %r", raw_text[:200])
        return dict(_TRIAGE_FALLBACK)

    category = data.get("category")
    priority = data.get("priority")
    action = data.get("action")

    if (
        category not in valid_categories
        or priority not in valid_priorities
        or not isinstance(action, str)
        or not action.strip()
    ):
        logger.warning("Triage response failed shape validation: %r", data)
        return dict(_TRIAGE_FALLBACK)

    return {"category": category, "priority": priority, "action": action.strip()}


# Module-level singleton, imported by the Flask app.
assistant = StadiumAssistant()
