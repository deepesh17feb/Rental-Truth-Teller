from agents.state import AddressResolved, GeoPoint, PricingAnalysis, VibeAnalysis, NearbyFacility, NeighbourhoodAnalysis, VerdictCard

def fallback_address_resolution(listing_input: str, error_msg: str) -> dict:
    """Fallback for Supervisor Agent geocoding."""
    fallback = AddressResolved(
        raw_address=listing_input[:100],
        structured_address="Whitefield, Bangalore, Karnataka",
        locality="Whitefield",
        geo=GeoPoint(lat=12.9698, lon=77.7500),
        confidence=0.4
    )
    return {
        "address_resolved": fallback,
        "messages": [f"[Supervisor Agent] Geocoding fallback used: {error_msg}"]
    }

def fallback_vibe_analysis(error_msg: str) -> dict:
    """Fallback for Vibe Check Agent."""
    return {
        "vibe_data": VibeAnalysis(
            amenity_vs_claim_diffs=["Unable to perform description NLP validation due to exception."],
            community_signals=[],
            diet_pet_lifestyle=[],
            listing_nlp_sentiment="Error"
        ),
        "messages": [f"[Vibe Check Agent] Error encountered: {error_msg}"]
    }

def fallback_neighbourhood_analysis(locality: str, metro_station: str) -> tuple[float, list[NearbyFacility]]:
    """Fallback logic for Neighbourhood Agent POIs."""
    base_metro_dist = 1.5
    facilities = [
        NearbyFacility(name=f"{locality} Central High School", facility_type="school", distance_km=1.2),
        NearbyFacility(name=f"{locality} Community Clinic", facility_type="hospital", distance_km=0.8),
        NearbyFacility(name=f"{locality} Supermarket", facility_type="market", distance_km=0.5),
        NearbyFacility(name=metro_station, facility_type="metro", distance_km=base_metro_dist)
    ]
    return base_metro_dist, facilities

def fallback_synthesis(rent: float, overpriced_percentage: float, total_upfront_cost: float, error_msg: str) -> dict:
    """Fallback for Synthesis Agent Verdict Card."""
    flat_verdict = VerdictCard(
        fair_range_min=rent * 0.85,
        fair_range_max=rent * 1.15,
        overpriced_percentage=overpriced_percentage,
        total_upfront_cost=total_upfront_cost,
        red_flags=["Failed to run composite synthesis, showing structural pricing alerts only."],
        neighbourhood_score=6.0,
        broker_questionnaire=["Why does the landlord charge this amount of rent?"]
    )
    return {
        "final_verdict": flat_verdict,
        "messages": [f"[Synthesis Agent] Synthesis error fallback: {error_msg}"]
    }
