# agents/supervisor.py
"""
agents/supervisor.py
────────────────────
Supervisor Agent: First entrypoint. Extracts locality/address from raw
listing text via LLM, then resolves real coordinates via Nominatim.
"""

from __future__ import annotations

import logging
from agents.config import get_llm
from agents.prompts import EXTRACT_LOCALITY_PROMPT
from agents.state import AgentState, AddressResolved, GeoPoint
from agents.fallbacks import fallback_address_resolution
from agents.llm_call import call_llm_structured, LLMCallError
from agents.schemas import LocalityExtractionResult
from agents.geocoding import geocode_address, GeocodingError

log = logging.getLogger(__name__)

def supervisor_node(state: AgentState) -> dict:
    log.info("[Supervisor Agent] Resolving address & geocoding listing…")

    listing_input = state.get("listing_input", "")
    if not listing_input:
        # Defaults fallback
        res = AddressResolved(
            raw_address="Bangalore",
            structured_address="Bangalore, Karnataka, IndiaIndex",
            locality="Bangalore",
            geo=GeoPoint(lat=12.9716, lon=77.5946),
            confidence=0.1
        )
        return {"address_resolved": res, "messages": ["[Supervisor Agent] No input listing provided; resolved global default."]}

    # Look up known target areas (from config.areas) before falling back to real geocoding
    from config.areas import TARGET_AREAS
    text_lower = listing_input.lower()
    for key, area_cfg in TARGET_AREAS.items():
        if key in text_lower or area_cfg.name.lower() in text_lower:
            resolved = AddressResolved(
                raw_address=listing_input[:100],
                structured_address=f"{area_cfg.name}, Bangalore, Karnataka, India",
                locality=area_cfg.name,
                geo=GeoPoint(lat=area_cfg.latitude, lon=area_cfg.longitude),
                confidence=0.9
            )
            msg = f"[Supervisor Agent] Geolocated to `{resolved.locality}` via static dictionary. Coords: ({resolved.geo.lat}, {resolved.geo.lon})."
            log.info(msg)
            return {
                "address_resolved": resolved,
                "messages": [msg]
            }

    llm = get_llm(temperature=0.1)

    try:
        extraction = call_llm_structured(llm, EXTRACT_LOCALITY_PROMPT, {"listing_input": listing_input}, LocalityExtractionResult)
        geo = geocode_address(extraction.structured_address or extraction.locality)

        resolved = AddressResolved(
            raw_address=listing_input[:100],
            structured_address=extraction.structured_address,
            locality=extraction.locality,
            geo=geo,
            confidence=0.9
        )

        msg = f"[Supervisor Agent] Geolocated to `{resolved.locality}` via OSM. Coords: ({resolved.geo.lat}, {resolved.geo.lon})."
        log.info(msg)
        return {
            "address_resolved": resolved,
            "messages": [msg]
        }
    except (LLMCallError, GeocodingError) as e:
        log.error(f"[Supervisor Agent] Address resolution failed: {e}")
        return fallback_address_resolution(listing_input, str(e))
