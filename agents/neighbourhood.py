"""
agents/neighbourhood.py
───────────────────────
Neighbourhood Agent: Analyzes local facilities, calculate metro distances, schools, 
hospitals, and generates mock Kibana map pin layout.
"""

from __future__ import annotations

import logging
import random
from agents.state import AgentState, NearbyFacility, NeighbourhoodAnalysis

log = logging.getLogger(__name__)

def neighbourhood_node(state: AgentState) -> dict:
    log.info("[Neighbourhood Agent] Analyzing neighborhood points of interest (POI)…")
    
    address_resolved = state.get("address_resolved")
    locality = address_resolved.locality if address_resolved else "Bangalore"
    
    # 1. Synthesize facility lookups based on the locality
    # We simulate a Places API / MCP proximity search
    # Whitefield: suburban, tech parks
    # Koramangala: dense, cafes
    loc_lower = locality.lower()
    
    facilities = []
    
    # Define candidate POIs depending on location
    if "whitefield" in loc_lower:
        metro_station = "Whitefield (Kadugodi) Metro Station"
        base_metro_dist = 1.2
        schools_list = [("The Deens Academy", 0.8), ("Vydehi School of Excellence", 1.5)]
        hospitals_list = [("Manipal Hospital Whitefield", 1.1), ("RxDx Healthcare", 2.0)]
        markets_list = [("Nexus Forum Shantiniketan Mall", 0.7), ("Reliance Fresh", 0.4)]
    elif "koramangala" in loc_lower:
        metro_station = "Trinity Metro Station / MG Road (Interchange)"
        base_metro_dist = 4.2 # Koramangala does not have metro inside yet
        schools_list = [("Bethany High School", 0.5), ("St. John's Medical College School", 1.2)]
        hospitals_list = [("St. John's National Academy", 0.9), ("Apollo Spectra Spectra", 1.6)]
        markets_list = [("Koramangala Club District", 0.3), ("SPAR Hypermarket", 1.1)]
    else:
        # Default Bangalore composite
        metro_station = f"{locality} Metro Station"
        base_metro_dist = round(random.uniform(0.5, 3.5), 1)
        schools_list = [(f"{locality} High School", 1.4)]
        hospitals_list = [(f"{locality} General Hospital", 2.1)]
        markets_list = [("Smart Bazar", 0.8)]

    # Standardize POI structures
    for name, dist in schools_list:
        facilities.append(NearbyFacility(name=name, facility_type="school", distance_km=dist))
    
    for name, dist in hospitals_list:
        facilities.append(NearbyFacility(name=name, facility_type="hospital", distance_km=dist))
        
    for name, dist in markets_list:
        facilities.append(NearbyFacility(name=name, facility_type="market", distance_km=dist))

    facilities.append(NearbyFacility(name=metro_station, facility_type="metro", distance_km=base_metro_dist))

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

    msg = f"[Neighbourhood Agent] Successfully catalogued local POIs. Metro: {metro_station} ({base_metro_dist}km)."
    log.info(msg)

    return {
        "neighbourhood_data": analysis_res,
        "messages": [msg]
    }
