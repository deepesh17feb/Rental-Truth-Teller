# agents/schemas.py
"""
agents/schemas.py
──────────────────
Pydantic models describing the exact JSON shape each remaining LLM prompt
in agents/prompts.py must return. Used with PydanticOutputParser (see
agents/llm_call.py) instead of hand-rolled JSON string scraping.

Geocoding and nearby-facility lookups no longer go through the LLM (see
agents/geocoding.py and agents/facilities.py) — LocalityExtractionResult
covers only the text-extraction step that still needs the LLM.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class LocalityExtractionResult(BaseModel):
    locality: str = Field(description="Target locality or area name in Bangalore, e.g. Whitefield, Koramangala")
    structured_address: str = Field(description="Cleaned, structured address string ending in Bangalore, Karnataka, suitable for a geocoding lookup")


class FinancialsResult(BaseModel):
    rent: float = Field(default=0.0, description="Monthly rent in INR, 0 if not found")
    deposit: float = Field(default=0.0, description="Security deposit in INR, 0 if not found")
    area_sqft: Optional[float] = Field(default=None, description="Property area in square feet, null if not found")


class BenchmarksResult(BaseModel):
    avg_price_per_sqft: float = Field(description="Typical average rent rate in INR per sqft for this locality")
    std_price_per_sqft: float = Field(description="Realistic standard deviation in INR per sqft for pricing variance")


class VibeResult(BaseModel):
    amenity_vs_claim_diffs: List[str] = Field(default_factory=list, description="Discrepancies between claims and reality found in the listing")
    community_signals: List[str] = Field(default_factory=list, description="Neighbourhood vibe and safety signals extracted from text")
    diet_pet_lifestyle: List[str] = Field(default_factory=list, description="Restrictive rules like food, pets, gender, marital status constraints")
    listing_nlp_sentiment: str = Field(default="Neutral", description="One word describing overall listing sentiment")


class SynthesisResult(BaseModel):
    fair_range_min: float = Field(description="Minimum of the dynamic fair rent range estimate")
    fair_range_max: float = Field(description="Maximum of the dynamic fair rent range estimate")
    overpriced_percentage: float = Field(description="Percentage the listing is overpriced relative to fair range, negative if underpriced")
    red_flags: List[str] = Field(default_factory=list, description="Extreme prices, strict lease terms, or POI deficiencies found")
    neighbourhood_score: float = Field(description="Score from 0 to 10 based on proximity to metro, schools, hospitals, markets")
    broker_questionnaire: List[str] = Field(default_factory=list, description="4 key clever questions to ask the broker or owner")
