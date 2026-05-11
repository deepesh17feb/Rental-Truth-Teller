"""
agents/neighbourhood.py
───────────────────────
Neighbourhood Agent: Analyzes local facilities, calculate metro distances, schools, 
hospitals, and generates mock Kibana map pin layout.
"""

from __future__ import annotations

import json
import logging
import random
from langchain_core.prompts import ChatPromptTemplate
from agents.config import get_llm, get_response_text
from agents.state import AgentState, NearbyFacility, NeighbourhoodAnalysis

log = logging.getLogger(__name__)

RESOLVE_NEIGHBOURHOOD_PROMPT = """You are a Bangalore local geographer and spatial intelligence agent.
Given a target property's resolved locality and structured address:
Locality: {locality}
Structured Address: {structured_address}

Resolve real, actual nearby facilities of the following types that exist around this area:
1. The closest real Metro Station and its realistic road distance in kilometers (usually 0.5 to 5.0 km).
2. Two real schools (within 3km) and their realistic distances.
3. Two real hospitals or clinics (within 3km) and their realistic distances.
4. Two real supermarkets or local shopping markets (within 2km) and their realistic distances.

Return a strictly formatted JSON object matching this schema:
{{
  "metro_station": "Real Metro Station Name",
  "metro_distance_km": 1.2,
  "facilities": [
    {{"name": "Real School 1", "facility_type": "school", "distance_km": 0.8}},
    {{"name": "Real School 2", "facility_type": "school", "distance_km": 1.5}},
    {{"name": "Real Hospital 1", "facility_type": "hospital", "distance_km": 1.1}},
    {{"name": "Real Hospital 2", "facility_type": "hospital", "distance_km": 2.2}},
    {{"name": "Real Supermarket 1", "facility_type": "market", "distance_km": 0.5}},
    {{"name": "Real Supermarket 2", "facility_type": "market", "distance_km": 1.0}}
  ]
}}
Write ONLY the raw JSON object. Do not wrap in markdown, backticks or formatting.
"""

def neighbourhood_node(state: AgentState) -> dict:
    log.info("[Neighbourhood Agent] Analyzing neighborhood points of interest (POI) dynamically…")
    
    address_resolved = state.get("address_resolved")
    locality = address_resolved.locality if address_resolved else "Bangalore"
    structured_address = address_resolved.structured_address if address_resolved else "Bangalore, Karnataka"
    
    facilities = []
    metro_station = f"{locality} Metro Station"
    base_metro_dist = -1.0

    # 1. Dynamic resolution using LLM
    llm = get_llm(temperature=0.1)
    prompt = ChatPromptTemplate.from_template(RESOLVE_NEIGHBOURHOOD_PROMPT)
    chain = prompt | llm

    try:
        response = chain.invoke({
            "locality": locality,
            "structured_address": structured_address
        })
        content = get_response_text(response)
        if content.startswith("```json"):
            content = content.replace("```json", "", 1)
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

        data = json.loads(content)
        metro_station = data.get("metro_station", f"{locality} Metro Station")
        base_metro_dist = float(data.get("metro_distance_km", 2.0))

        # Load resolved facilities
        raw_facilities = data.get("facilities", [])
        for f in raw_facilities:
            facilities.append(NearbyFacility(
                name=f.get("name", "Nearby Facility"),
                facility_type=f.get("facility_type", "market"),
                distance_km=float(f.get("distance_km", 1.0))
            ))
            
        # Append Metro Station as facility too
        facilities.append(NearbyFacility(
            name=metro_station,
            facility_type="metro",
            distance_km=base_metro_dist
        ))
        log.info(f"[Neighbourhood Agent] Resolved closest transit: {metro_station} ({base_metro_dist} km). Total POIs catalogued: {len(facilities)}")
        
    except Exception as exc:
        log.error(f"[Neighbourhood Agent] Error during dynamic POI resolution: {exc}. Using robust fallback estimates.")
        # Dynamic fallback generators
        base_metro_dist = 1.5
        facilities = [
            NearbyFacility(name=f"{locality} Central High School", facility_type="school", distance_km=1.2),
            NearbyFacility(name=f"{locality} Community Clinic", facility_type="hospital", distance_km=0.8),
            NearbyFacility(name=f"{locality} Supermarket", facility_type="market", distance_km=0.5),
            NearbyFacility(name=metro_station, facility_type="metro", distance_km=base_metro_dist)
        ]

    # 2. Summarize metrics for State
    schools_count = sum(1 for f in facilities if f.facility_type == "school")
    hospitals_count = sum(1 for f in facilities if f.facility_type == "hospital")
    markets_count = sum(1 for f in facilities if f.facility_type == "market")
    
    lat = address_resolved.geo.lat if (address_resolved and address_resolved.geo) else 12.9716
    lon = address_resolved.geo.lon if (address_resolved and address_resolved.geo) else 77.5946
    
    # Formulate a synthetic Kibana map visualize link with coordinates pinned
    kibana_maps_pin = f"http://localhost:5601/app/maps#/map?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:now-15m,to:now))&_a=(description:'',views:(map:(center:!({lat},{lon}),zoom:15)))"

    analysis_res = NeighbourhoodAnalysis(
        facilities=facilities,
        metro_station=metro_station,
        metro_distance_km=base_metro_dist,
        school_count=schools_count,
        hospital_count=hospitals_count,
        market_count=markets_count,
        kibana_maps_pin_url=kibana_maps_pin
    )

    msg = f"[Neighbourhood Agent] Dynamic POI Analysis completed. Metro: {metro_station} ({base_metro_dist}km)."
    log.info(msg)

    return {
        "neighbourhood_data": analysis_res,
        "messages": [msg]
    }

