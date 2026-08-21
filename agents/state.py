"""
agents/state.py
───────────────
LangGraph state definition and structures for the Rental Truth-Teller.
"""

from __future__ import annotations

from typing import Annotated, List, Optional, TypedDict
from pydantic import BaseModel, Field


class GeoPoint(BaseModel):
    lat: float
    lon: float


class AddressResolved(BaseModel):
    raw_address: str
    structured_address: str = ""
    locality: str = ""                  # e.g. "Whitefield"
    city: str = "Bangalore"
    geo: Optional[GeoPoint] = None
    confidence: float = 1.0
    used_fallback: bool = False


class PricingAnalysis(BaseModel):
    rent_amount: float = 0.0
    deposit_amount: float = 0.0
    deposit_multiplier: float = 0.0   # deposit / rent
    deposit_is_normal: bool = True     # True if within normal multiplier (e.g. <= 10x, ideally ~5-10x)
    area_sqft: Optional[float] = None
    price_per_sqft: Optional[float] = None
    market_avg_price_per_sqft: float = 0.0
    market_std_price_per_sqft: float = 0.0
    overpriced_percentage: float = 0.0  # positive if overpriced, negative if underpriced
    price_drift_flag: bool = False      # True if > 1.5 stddev above average
    used_fallback: bool = False


class VibeAnalysis(BaseModel):
    amenity_vs_claim_diffs: List[str] = Field(default_factory=list)  # list of claims that don't match facts
    community_signals: List[str] = Field(default_factory=list)       # neighborhood vibes, safety signals
    diet_pet_lifestyle: List[str] = Field(default_factory=list)      # structural/societal rules flag (e.g. "veg only")
    listing_nlp_sentiment: str = "Neutral"
    used_fallback: bool = False


class NearbyFacility(BaseModel):
    name: str
    facility_type: str                  # "school" | "hospital" | "metro" | "market"
    distance_km: float


class NeighbourhoodAnalysis(BaseModel):
    facilities: List[NearbyFacility] = Field(default_factory=list)
    metro_station: str = ""
    metro_distance_km: float = -1.0     # -1 if unknown/none
    school_count: int = 0
    hospital_count: int = 0
    market_count: int = 0
    kibana_maps_pin_url: str = ""       # generated visualization URL or pin summary
    used_fallback: bool = False


class VerdictCard(BaseModel):
    fair_range_min: float = 0.0
    fair_range_max: float = 0.0
    overpriced_percentage: float = 0.0
    total_upfront_cost: float = 0.0      # deposit + first month rent + standard fees
    red_flags: List[str] = Field(default_factory=list)
    neighbourhood_score: float = 0.0    # 0 to 10 scale
    broker_questionnaire: List[str] = Field(default_factory=list) # exact questions to ask the broker/owner
    used_fallback: bool = False


from operator import add

class AgentState(TypedDict):
    # User Input
    listing_input: str                  # The raw text description or property page input

    # Inter-agent resolved states
    address_resolved: Optional[AddressResolved]
    pricing_data: Optional[PricingAnalysis]
    vibe_data: Optional[VibeAnalysis]
    neighbourhood_data: Optional[NeighbourhoodAnalysis]

    # Final Compiled Outcome
    final_verdict: Optional[VerdictCard]

    # Execution Log/trace messages
    messages: Annotated[List[str], add]
