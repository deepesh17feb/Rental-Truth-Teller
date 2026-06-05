"""
agents/neighbourhood.py
───────────────────────
Neighbourhood Agent: Analyzes local facilities, calculate metro distances, schools, 
hospitals, and generates mock Kibana map pin layout.
"""

from __future__ import annotations

import logging
import random
from langchain_core.prompts import ChatPromptTemplate
from agents.config import get_llm, get_response_text
from agents.prompts import RESOLVE_NEIGHBOURHOOD_PROMPT
from agents.state import AgentState, NearbyFacility, NeighbourhoodAnalysis
from agents.fallbacks import fallback_neighbourhood_analysis
from agents.utils import parse_json_from_llm

log = logging.getLogger(__name__)

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
        data = parse_json_from_llm(content)

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
        base_metro_dist, facilities = fallback_neighbourhood_analysis(locality, metro_station)

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

