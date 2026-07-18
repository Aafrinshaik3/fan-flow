import random

import pytest

from services.crowd_monitor import ZONES, get_snapshot, suggest_alternate_gate
from services.security import RateLimiter, ValidationError, sanitize_text


class TestCrowdMonitor:
    def test_snapshot_covers_every_zone(self):
        snapshot = get_snapshot(rng=random.Random(42))
        zone_names = {z.zone for z in snapshot.zones}
        assert zone_names == set(ZONES)

    def test_snapshot_is_deterministic_with_seeded_rng(self):
        snap_a = get_snapshot(rng=random.Random(7))
        snap_b = get_snapshot(rng=random.Random(7))
        assert [z.occupancy_pct for z in snap_a.zones] == [
            z.occupancy_pct for z in snap_b.zones
        ]

    @pytest.mark.parametrize(
        "occupancy,expected_level",
        [(10, "normal"), (74, "normal"), (75, "warning"), (91, "warning"), (92, "critical"), (99, "critical")],
    )
    def test_level_classification_thresholds(self, occupancy, expected_level):
        # Force every zone to the same occupancy value to test the boundary.
        class FixedRandom(random.Random):
            def randint(self, a, b):
                return occupancy

        snapshot = get_snapshot(rng=FixedRandom())
        assert all(z.level == expected_level for z in snapshot.zones)

    def test_suggest_alternate_gate_picks_quietest_zone(self):
        snapshot = get_snapshot(rng=random.Random(1))
        quietest = min(snapshot.zones, key=lambda z: z.occupancy_pct)
        suggestion = suggest_alternate_gate(snapshot)
        assert quietest.zone in suggestion

    def test_suggest_alternate_gate_handles_empty_snapshot(self):
        from services.crowd_monitor import CrowdSnapshot

        assert "No zone data" in suggest_alternate_gate(CrowdSnapshot())


class TestSanitizeText:
    def test_accepts_clean_text(self):
        assert sanitize_text("Where is Gate C?", max_length=50) == "Where is Gate C?"

    def test_strips_control_characters(self):
        assert sanitize_text("hi\x00there", max_length=50) == "hithere"

    def test_rejects_none(self):
        with pytest.raises(ValidationError):
            sanitize_text(None, max_length=50)

    def test_rejects_empty_after_stripping(self):
        with pytest.raises(ValidationError):
            sanitize_text("   ", max_length=50)

    def test_rejects_non_string(self):
        with pytest.raises(ValidationError):
            sanitize_text(12345, max_length=50)

    def test_rejects_too_long(self):
        with pytest.raises(ValidationError):
            sanitize_text("a" * 51, max_length=50)


class TestParseTriageResponse:
    def test_parses_valid_json(self):
        from services.ai_assistant import parse_triage_response

        raw = (
            '{"category": "crowd", "priority": "high", '
            '"action": "Dispatch two stewards to Gate B."}'
        )
        result = parse_triage_response(raw)
        assert result == {
            "category": "crowd",
            "priority": "high",
            "action": "Dispatch two stewards to Gate B.",
        }

    def test_falls_back_on_malformed_json(self):
        from services.ai_assistant import _TRIAGE_FALLBACK, parse_triage_response

        assert parse_triage_response("not json at all") == _TRIAGE_FALLBACK

    def test_falls_back_on_invalid_category(self):
        from services.ai_assistant import _TRIAGE_FALLBACK, parse_triage_response

        raw = '{"category": "banana", "priority": "high", "action": "do something"}'
        assert parse_triage_response(raw) == _TRIAGE_FALLBACK

    def test_falls_back_on_invalid_priority(self):
        from services.ai_assistant import _TRIAGE_FALLBACK, parse_triage_response

        raw = '{"category": "medical", "priority": "extreme", "action": "call 911"}'
        assert parse_triage_response(raw) == _TRIAGE_FALLBACK

    def test_falls_back_on_missing_action(self):
        from services.ai_assistant import _TRIAGE_FALLBACK, parse_triage_response

        raw = '{"category": "medical", "priority": "critical", "action": ""}'
        assert parse_triage_response(raw) == _TRIAGE_FALLBACK

    def test_falls_back_when_wrapped_in_extra_text(self):
        # Models sometimes ignore "JSON only" instructions; confirm we fail
        # safe rather than trying to regex-extract embedded JSON.
        from services.ai_assistant import _TRIAGE_FALLBACK, parse_triage_response

        raw = 'Here is the classification: {"category": "medical", "priority": "high", "action": "x"}'
        assert parse_triage_response(raw) == _TRIAGE_FALLBACK


class TestStadiumAssistantTriage:
    def test_triage_falls_back_without_api_key(self):
        from services.ai_assistant import _TRIAGE_FALLBACK, StadiumAssistant

        unconfigured = StadiumAssistant(api_key="")
        assert unconfigured.triage_incident("Fire near Gate A") == _TRIAGE_FALLBACK

    def test_ask_falls_back_without_api_key(self):
        from services.ai_assistant import StadiumAssistant

        unconfigured = StadiumAssistant(api_key="")
        reply = unconfigured.ask("Where is Gate C?")
        assert reply.degraded is True


class TestRateLimiter:
    def test_allows_up_to_the_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        assert limiter.allow("client-1")
        assert limiter.allow("client-1")
        assert limiter.allow("client-1")
        assert not limiter.allow("client-1")

    def test_tracks_clients_independently(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        assert limiter.allow("client-a")
        assert limiter.allow("client-b")
        assert not limiter.allow("client-a")
