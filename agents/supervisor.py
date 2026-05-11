"""
agents/supervisor.py
────────────────────
Supervisor Agent: First entrypoint. Performs geocoding / address resolution 
from raw listing input text to populate shared agent parameters.
"""

from __future__ import annotations

import json
import logging
from langchain_core.prompts import ChatPromptTemplate
from agents.config import get_llm, get_response_text
from agents.state import AgentState, AddressResolved, GeoPoint

log = logging.getLogger(__name__)

GEOCODE_PROMPT = """You are a Bangalore spatial resolver agent.
Analyze the given rental property listing content and extract:
1. The target locality or area in Bangalore (e.g. Whitefield, Koramangala, Indiranagar, HSR Layout).
2. A cleaned, structured address.
3. A sensible latitude/longitude geopoint estimate for this locality in Bangalore.

Raw Listing Content:
{listing_input}

Return a strictly formatted JSON:
{{
  "locality": "Locality Name",
  "structured_address": "Cleaned Address, Bangalore, Karnataka",
  "lat": 12.9716, // estimated latitude
  "lon": 77.5946  // estimated longitude
}}
Ensure you write ONLY the raw JSON block. Do not wrap in markdown codeblocks.
"""

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
        if content.startswith("```json"):
            content = content.replace("```json", "", 1)
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()
        
        data = json.loads(content)
        
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
        # Fallback geocoding
        fallback = AddressResolved(
            raw_address=listing_input[:100],
            structured_address="Whitefield, Bangalore, Karnataka",
            locality="Whitefield",
            geo=GeoPoint(lat=12.9698, lon=77.7500),
            confidence=0.4
        )
        return {
            "address_resolved": fallback,
            "messages": [f"[Supervisor Agent] Geocoding fallback used: {str(e)}"]
        }
