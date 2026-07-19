"""
FanFlow AI -- Flask application entrypoint.

Routes:
    GET  /                 Serves the fan/staff-facing web app.
    POST /api/chat         GenAI multilingual wayfinding & help assistant.
    GET  /api/crowd        Current crowd-density snapshot across zones.
    POST /api/navigate     Suggests the least-congested gate/zone right now.
    GET  /healthz          Liveness probe for deployment platforms.
"""
from __future__ import annotations

import logging

from flask import Flask, jsonify, render_template, request

from config import config
from services.ai_assistant import assistant
from services.crowd_monitor import get_snapshot, suggest_alternate_gate
from services.security import RateLimiter, ValidationError, sanitize_text
from services.sustainability import get_sustainability_snapshot, suggest_transport_option

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = config.secret_key or "dev-only-not-for-production"
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024  # 32 KB: chat payloads are tiny

_chat_limiter = RateLimiter(max_requests=config.rate_limit_per_minute)

for problem in config.validate():
    logger.warning("Config warning: %s", problem)


def _client_key() -> str:
    """Best-effort client identity for rate limiting (demo-grade)."""
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")


@app.after_request
def add_security_headers(response):
    """Baseline security headers for every response."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    origin = request.headers.get("Origin")
    if origin in config.allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    return response


@app.errorhandler(ValidationError)
def handle_validation_error(err: ValidationError):
    return jsonify({"error": str(err)}), 400


@app.errorhandler(404)
def handle_not_found(_err):
    return jsonify({"error": "Not found."}), 404


@app.errorhandler(500)
def handle_server_error(err):
    logger.exception("Unhandled server error: %s", err)
    return jsonify({"error": "Something went wrong. Please try again."}), 500


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok", "assistant_configured": assistant.is_configured})


@app.route("/api/chat", methods=["POST"])
def chat():
    if not _chat_limiter.allow(_client_key()):
        return jsonify({"error": "Too many requests. Please wait a moment."}), 429

    payload = request.get_json(silent=True) or {}
    message = sanitize_text(
        payload.get("message"),
        max_length=config.max_message_length,
        field_name="message",
    )

    # History is optional and capped to the last 6 turns to bound both
    # request size and per-call cost.
    raw_history = payload.get("history") or []
    history = [
        {"role": turn.get("role"), "content": turn.get("content")}
        for turn in raw_history[-6:]
        if turn.get("role") in {"user", "assistant"} and turn.get("content")
    ]

    reply = assistant.ask(message, history=history)
    return jsonify({"reply": reply.text, "degraded": reply.degraded})


@app.route("/api/crowd", methods=["GET"])
def crowd():
    snapshot = get_snapshot()
    return jsonify(
        {
            "zones": [
                {
                    "zone": z.zone,
                    "occupancy_pct": z.occupancy_pct,
                    "level": z.level,
                    "recommendation": z.recommendation,
                }
                for z in snapshot.zones
            ],
            "critical_count": len(snapshot.critical_zones),
        }
    )


@app.route("/api/navigate", methods=["POST"])
def navigate():
    snapshot = get_snapshot()
    return jsonify({"suggestion": suggest_alternate_gate(snapshot)})


@app.route("/api/incident", methods=["POST"])
def incident():
    """Staff/volunteer workflow: triage a free-text incident report."""
    if not _chat_limiter.allow(_client_key()):
        return jsonify({"error": "Too many requests. Please wait a moment."}), 429

    payload = request.get_json(silent=True) or {}
    description = sanitize_text(
        payload.get("description"),
        max_length=config.max_message_length,
        field_name="description",
    )

    result = assistant.triage_incident(description)
    return jsonify(result)


@app.route("/api/sustainability", methods=["GET"])
def sustainability():
    snapshot = get_sustainability_snapshot()
    return jsonify(
        {
            "bins": [
                {
                    "station": b.station,
                    "fill_pct": b.fill_pct,
                    "level": b.level,
                    "recommendation": b.recommendation,
                }
                for b in snapshot.bins
            ],
            "critical_count": len(snapshot.critical_bins),
        }
    )


@app.route("/api/transport", methods=["POST"])
def transport():
    payload = request.get_json(silent=True) or {}
    distance_raw = payload.get("distance_km")

    try:
        distance_km = float(distance_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "distance_km must be a number."}), 400

    try:
        result = suggest_transport_option(distance_km)
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=config.debug)
