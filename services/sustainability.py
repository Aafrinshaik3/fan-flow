"""
Sustainability & transportation intelligence.

Addresses the "sustainability" and "transportation" pillars named directly
in the challenge brief, which the crowd/chat/triage features don't cover:
- Recycling/waste station monitoring, so bins get emptied before overflow
  instead of after someone complains.
- A transport advisory that steers fans toward lower-carbon options
  (public transit / shuttle) over solo rideshare/driving when a reasonable
  alternative exists, with an estimated CO2 saving to make the tradeoff
  concrete rather than abstract.

Like crowd_monitor.py, telemetry is simulated behind a clean function
boundary so the decision logic is fully real and testable today, and can
be pointed at real waste-sensor / transit-API data later.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

_BIN_WARNING_THRESHOLD = 70
_BIN_CRITICAL_THRESHOLD = 90

RECYCLING_STATIONS: tuple[str, ...] = (
    "Gate A - North Concourse",
    "Gate B - East Concourse",
    "Gate C - South Concourse",
    "Gate D - West Concourse",
    "Fan Zone Plaza",
)

# Rough, illustrative CO2-per-passenger-km figures (grams). Not a scientific
# claim -- used only to make the transit-vs-rideshare tradeoff concrete for
# a fan deciding how to get home.
_CO2_G_PER_KM = {
    "shuttle": 30,
    "public_transit": 40,
    "rideshare_shared": 65,
    "rideshare_solo": 120,
}


@dataclass
class BinStatus:
    station: str
    fill_pct: int
    level: str  # "ok" | "warning" | "critical"
    recommendation: str


@dataclass
class SustainabilitySnapshot:
    bins: list[BinStatus] = field(default_factory=list)

    @property
    def critical_bins(self) -> list[BinStatus]:
        return [b for b in self.bins if b.level == "critical"]


def _classify_bin(fill_pct: int) -> str:
    if fill_pct >= _BIN_CRITICAL_THRESHOLD:
        return "critical"
    if fill_pct >= _BIN_WARNING_THRESHOLD:
        return "warning"
    return "ok"


def _bin_recommendation(station: str, level: str) -> str:
    if level == "critical":
        return f"Dispatch waste collection to {station} now -- bin is nearly full."
    if level == "warning":
        return f"Schedule a collection pass at {station} within the hour."
    return f"{station} recycling station is within normal capacity."


def get_sustainability_snapshot(rng: random.Random | None = None) -> SustainabilitySnapshot:
    """
    Produce a current recycling/waste snapshot across monitored stations.

    A `random.Random` can be injected for deterministic tests, mirroring
    the pattern used in crowd_monitor.get_snapshot.
    """
    rng = rng or random.Random()
    snapshot = SustainabilitySnapshot()
    for station in RECYCLING_STATIONS:
        fill_pct = rng.randint(10, 99)
        level = _classify_bin(fill_pct)
        snapshot.bins.append(
            BinStatus(
                station=station,
                fill_pct=fill_pct,
                level=level,
                recommendation=_bin_recommendation(station, level),
            )
        )
    return snapshot


def suggest_transport_option(distance_km: float) -> dict:
    """
    Recommend the lowest-carbon reasonable way home for a given distance,
    with an estimated CO2 saving versus solo rideshare to make the
    trade-off concrete.

    Raises ValueError for a non-positive distance so callers can return a
    clean 400 rather than a confusing downstream calculation.
    """
    if distance_km <= 0:
        raise ValueError("distance_km must be positive")

    solo_emissions = _CO2_G_PER_KM["rideshare_solo"] * distance_km

    if distance_km <= 3:
        mode = "shuttle"
        note = "Short distance -- the free shuttle is fastest and lowest-carbon."
    elif distance_km <= 15:
        mode = "public_transit"
        note = "Public transit covers this distance well and cuts your footprint significantly."
    else:
        mode = "rideshare_shared"
        note = "For this distance, a shared rideshare is the lowest-carbon practical option."

    mode_emissions = _CO2_G_PER_KM[mode] * distance_km
    co2_saved_g = round(solo_emissions - mode_emissions)

    return {
        "recommended_mode": mode,
        "note": note,
        "estimated_co2_saved_g": max(co2_saved_g, 0),
    }
