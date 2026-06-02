"""
agents/supervisor.py
────────────────────
Supervisor Agent: First entrypoint. Performs geocoding / address resolution 
from raw listing input text to populate shared agent parameters.
"""

from __future__ import annotations

import logging
from langchain_core.prompts import ChatPromptTemplate
from agents.config import get_llm, get_response_text
from agents.prompts import GEOCODE_PROMPT
from agents.state import AgentState, AddressResolved, GeoPoint
from agents.fallbacks import fallback_address_resolution
from agents.utils import parse_json_from_llm

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

    llm = get_llm(temperature=0.1)
    prompt = ChatPromptTemplate.from_template(GEOCODE_PROMPT)
    chain = prompt | llm

    try:
        response = chain.invoke({"listing_input": listing_input})
        content = get_response_text(response)
        data = parse_json_from_llm(content)
        
        # Rely directly on coordinates from LLM resolution, or default to Bangalore Center
        lat = float(data.get("lat", 12.9716))
        lon = float(data.get("lon", 77.5946))
        locality = data.get("locality", "Whitefield")

        resolved = AddressResolved(
            raw_address=listing_input[:100],
            structured_address=data.get("structured_address", ""),
            locality=locality,
            geo=GeoPoint(lat=lat, lon=lon),
            confidence=0.9
        )
        
        msg = f"[Supervisor Agent] Geolocated to `{resolved.locality}`. Coords: ({resolved.geo.lat}, {resolved.geo.lon})."
        log.info(msg)
        return {
            "address_resolved": resolved,
            "messages": [msg]
        }
    except Exception as e:
        log.error(f"[Supervisor Agent] Address resolution parsing error: {e}")
        return fallback_address_resolution(listing_input, str(e))
