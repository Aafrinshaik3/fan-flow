import pytest

import app as app_module
from services.ai_assistant import AssistantReply


@pytest.fixture
def client():
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    # Each test gets a clean rate-limit window so tests don't interfere.
    app_module._chat_limiter = app_module.RateLimiter(
        max_requests=app_module.config.rate_limit_per_minute
    )


class TestIndexAndHealth:
    def test_index_serves_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"FanFlow" in resp.data

    def test_healthz_reports_status(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"


class TestCrowdAndNavigate:
    def test_crowd_endpoint_returns_all_zones(self, client):
        resp = client.get("/api/crowd")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["zones"]) == 6
        assert "critical_count" in data

    def test_navigate_endpoint_returns_suggestion(self, client):
        resp = client.post("/api/navigate")
        assert resp.status_code == 200
        assert "suggestion" in resp.get_json()


class TestSustainabilityEndpoints:
    def test_sustainability_endpoint_returns_all_stations(self, client):
        resp = client.get("/api/sustainability")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["bins"]) == 5
        assert "critical_count" in data

    def test_transport_endpoint_returns_suggestion(self, client):
        resp = client.post("/api/transport", json={"distance_km": 5})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["recommended_mode"] in {
            "shuttle", "public_transit", "rideshare_shared",
        }

    def test_transport_endpoint_rejects_missing_distance(self, client):
        resp = client.post("/api/transport", json={})
        assert resp.status_code == 400

    def test_transport_endpoint_rejects_non_numeric_distance(self, client):
        resp = client.post("/api/transport", json={"distance_km": "far"})
        assert resp.status_code == 400

    def test_transport_endpoint_rejects_negative_distance(self, client):
        resp = client.post("/api/transport", json={"distance_km": -3})
        assert resp.status_code == 400


class TestIncidentEndpoint:
    def test_rejects_missing_description(self, client):
        resp = client.post("/api/incident", json={})
        assert resp.status_code == 400

    def test_rejects_overlong_description(self, client):
        resp = client.post("/api/incident", json={"description": "a" * 1000})
        assert resp.status_code == 400

    def test_returns_triage_result(self, client, monkeypatch):
        monkeypatch.setattr(
            app_module.assistant,
            "triage_incident",
            lambda description: {
                "category": "crowd",
                "priority": "high",
                "action": "Dispatch stewards to Gate B.",
            },
        )
        resp = client.post(
            "/api/incident", json={"description": "Crowd surge at Gate B"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["priority"] == "high"
        assert data["category"] == "crowd"

    def test_enforces_rate_limit(self, client, monkeypatch):
        monkeypatch.setattr(
            app_module.assistant,
            "triage_incident",
            lambda description: {"category": "other", "priority": "low", "action": "ok"},
        )
        app_module._chat_limiter = app_module.RateLimiter(max_requests=1)

        resp1 = client.post("/api/incident", json={"description": "minor spill"})
        assert resp1.status_code == 200

        resp2 = client.post("/api/incident", json={"description": "minor spill"})
        assert resp2.status_code == 429


class TestChatEndpoint:
    def test_rejects_missing_message(self, client):
        resp = client.post("/api/chat", json={})
        assert resp.status_code == 400

    def test_rejects_overlong_message(self, client):
        resp = client.post("/api/chat", json={"message": "a" * 1000})
        assert resp.status_code == 400

    def test_returns_assistant_reply(self, client, monkeypatch):
        monkeypatch.setattr(
            app_module.assistant,
            "ask",
            lambda message, history=None: AssistantReply(text="Gate C is to your left."),
        )
        resp = client.post("/api/chat", json={"message": "Where is Gate C?"})
        assert resp.status_code == 200
        assert resp.get_json()["reply"] == "Gate C is to your left."

    def test_enforces_rate_limit(self, client, monkeypatch):
        monkeypatch.setattr(
            app_module.assistant,
            "ask",
            lambda message, history=None: AssistantReply(text="ok"),
        )
        app_module._chat_limiter = app_module.RateLimiter(max_requests=2)

        for _ in range(2):
            resp = client.post("/api/chat", json={"message": "hi"})
            assert resp.status_code == 200

        resp = client.post("/api/chat", json={"message": "hi"})
        assert resp.status_code == 429

    def test_history_is_capped_and_filtered(self, client, monkeypatch):
        captured = {}

        def fake_ask(message, history=None):
            captured["history"] = history
            return AssistantReply(text="ok")

        monkeypatch.setattr(app_module.assistant, "ask", fake_ask)

        long_history = [
            {"role": "user", "content": f"turn {i}"} for i in range(10)
        ] + [{"role": "not-a-real-role", "content": "should be dropped"}]

        client.post("/api/chat", json={"message": "hi", "history": long_history})
        assert len(captured["history"]) <= 6
        assert all(turn["role"] in {"user", "assistant"} for turn in captured["history"])
