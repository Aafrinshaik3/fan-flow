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
