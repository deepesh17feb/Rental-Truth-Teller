# agents/neighbourhood.py
"""
agents/neighbourhood.py
───────────────────────
Neighbourhood Agent: Finds real nearby schools, hospitals, markets, and
metro stations via OpenStreetMap Overpass, and generates a Kibana map pin.
"""

from __future__ import annotations

import logging
from agents.state import AgentState, GeoPoint, NeighbourhoodAnalysis
from agents.fallbacks import fallback_neighbourhood_analysis
from agents.facilities import find_nearby_facilities, FacilityLookupError
from agents.cache import cached_locality_lookup

log = logging.getLogger(__name__)

def neighbourhood_node(state: AgentState) -> dict:
    log.info("[Neighbourhood Agent] Analyzing neighborhood points of interest (POI)…")

    address_resolved = state.get("address_resolved")
    locality = address_resolved.locality if address_resolved else "Bangalore"

    metro_station = f"{locality} Metro Station"
    base_metro_dist = -1.0
    used_fallback = False

    geo = address_resolved.geo if (address_resolved and address_resolved.geo) else GeoPoint(lat=12.9716, lon=77.5946)

    try:
        facilities = cached_locality_lookup(
            f"neighbourhood:{locality}",
            lambda: find_nearby_facilities(geo),
        )

        metro_facility = next((f for f in facilities if f.facility_type == "metro"), None)
        if metro_facility:
            metro_station = metro_facility.name
            base_metro_dist = metro_facility.distance_km

        log.info(f"[Neighbourhood Agent] Resolved closest transit: {metro_station} ({base_metro_dist} km). Total POIs catalogued: {len(facilities)}")

    except FacilityLookupError as exc:
        log.error(f"[Neighbourhood Agent] Error during POI lookup: {exc}. Using robust fallback estimates.")
        base_metro_dist, facilities = fallback_neighbourhood_analysis(locality, metro_station)
        used_fallback = True

    # Summarize metrics for State
    schools_count = sum(1 for f in facilities if f.facility_type == "school")
    hospitals_count = sum(1 for f in facilities if f.facility_type == "hospital")
    markets_count = sum(1 for f in facilities if f.facility_type == "market")

    lat = geo.lat
    lon = geo.lon

    # Formulate a synthetic Kibana map visualize link with coordinates pinned
    kibana_maps_pin = f"http://localhost:5601/app/maps#/map?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:now-15m,to:now))&_a=(description:'',views:(map:(center:!({lat},{lon}),zoom:15)))"

    analysis_res = NeighbourhoodAnalysis(
        facilities=facilities,
        metro_station=metro_station,
        metro_distance_km=base_metro_dist,
        school_count=schools_count,
        hospital_count=hospitals_count,
        market_count=markets_count,
        kibana_maps_pin_url=kibana_maps_pin,
        used_fallback=used_fallback
    )

    msg = f"[Neighbourhood Agent] POI lookup completed. Metro: {metro_station} ({base_metro_dist}km)."
    log.info(msg)

    return {
        "neighbourhood_data": analysis_res,
        "messages": [msg]
    }
