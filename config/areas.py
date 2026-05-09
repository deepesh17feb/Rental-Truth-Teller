"""
config/areas.py
───────────────
Defines the 2 target Bangalore areas with metadata used
to construct search URLs for each source website.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class AreaConfig:
    """Represents a crawl-target locality in Bangalore."""

    name: str                        # Human-readable locality name
    city: str = "Bangalore"
    latitude: float = 0.0
    longitude: float = 0.0

    # Per-source slug / ID used inside URLs
    magicbricks_slug: str = ""       # e.g. "whitefield-bangalore"
    nintyacres_slug: str = ""        # e.g. "whitefield"
    nobroker_slug: str = ""          # e.g. "whitefield"


# ─────────────────────────────────────────────────────────────────────────────
# TWO TARGET AREAS IN BANGALORE
# ─────────────────────────────────────────────────────────────────────────────

TARGET_AREAS: Dict[str, AreaConfig] = {
    "whitefield": AreaConfig(
        name="Whitefield",
        city="Bangalore",
        latitude=12.9698,
        longitude=77.7500,
        magicbricks_slug="Whitefield-Bangalore",
        nintyacres_slug="whitefield-bangalore",
        nobroker_slug="whitefield",
    ),
    "koramangala": AreaConfig(
        name="Koramangala",
        city="Bangalore",
        latitude=12.9352,
        longitude=77.6245,
        magicbricks_slug="Koramangala-Bangalore",
        nintyacres_slug="koramangala-bangalore",
        nobroker_slug="koramangala",
    ),
}
