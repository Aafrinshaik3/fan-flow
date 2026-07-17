"""
Crowd management & operational intelligence.

In a real deployment this would ingest turnstile counters, CCTV people-
counting feeds, and Wi-Fi/BLE density estimates. Here it simulates that
telemetry so the decision logic -- the actual GenAI-adjacent operational
intelligence piece the challenge asks for -- can be demonstrated and
unit-tested deterministically (a seeded RNG is injected, never global
random state).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

# Density thresholds, expressed as % of a zone's safe capacity.
_WARNING_THRESHOLD = 75
_CRITICAL_THRESHOLD = 92

ZONES: tuple[str, ...] = (
    "Gate A - North Concourse",
    "Gate B - East Concourse",
    "Gate C - South Concourse",
    "Gate D - West Concourse",
    "Fan Zone Plaza",
    "Transit Hub - Shuttle Bay",
)


@dataclass
class ZoneStatus:
    zone: str
    occupancy_pct: int
    level: str  # "normal" | "warning" | "critical"
    recommendation: str


@dataclass
class CrowdSnapshot:
    zones: list[ZoneStatus] = field(default_factory=list)

    @property
    def critical_zones(self) -> list[ZoneStatus]:
        return [z for z in self.zones if z.level == "critical"]


def _classify(occupancy_pct: int) -> str:
    if occupancy_pct >= _CRITICAL_THRESHOLD:
        return "critical"
    if occupancy_pct >= _WARNING_THRESHOLD:
        return "warning"
    return "normal"


def _recommend(zone: str, level: str) -> str:
    if level == "critical":
        return (
            f"Redirect incoming fans away from {zone}; open overflow queuing "
            f"and dispatch additional stewards."
        )
    if level == "warning":
        return f"Monitor {zone} closely; consider staging stewards nearby."
    return f"{zone} is operating normally."


def get_snapshot(rng: random.Random | None = None) -> CrowdSnapshot:
    """
    Produce a current crowd-density snapshot across all monitored zones.

    A `random.Random` instance can be injected for deterministic tests;
    defaults to a fresh instance (not the shared global RNG) to avoid
    cross-request interference in a multi-threaded server.
    """
    rng = rng or random.Random()
    snapshot = CrowdSnapshot()
    for zone in ZONES:
        occupancy = rng.randint(30, 99)
        level = _classify(occupancy)
        snapshot.zones.append(
            ZoneStatus(
                zone=zone,
                occupancy_pct=occupancy,
                level=level,
                recommendation=_recommend(zone, level),
            )
        )
    return snapshot


def suggest_alternate_gate(current_snapshot: CrowdSnapshot) -> str:
    """Suggest the least-congested zone for a fan currently facing a queue."""
    if not current_snapshot.zones:
        return "No zone data available right now."
    quietest = min(current_snapshot.zones, key=lambda z: z.occupancy_pct)
    return (
        f"{quietest.zone} currently has the shortest wait "
        f"({quietest.occupancy_pct}% capacity)."
    )
