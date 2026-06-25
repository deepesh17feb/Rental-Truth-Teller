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

EXTRACT_FINANCIALS_PROMPT = """You are a property financial extractor. Given the raw property description, extract:
1. Monthly Rent in INR.
2. Security Deposit in INR.
3. Property Area in SqFt.

Raw listing content:
{listing_input}

Return a strictly formatted JSON object:
{{
  "rent": float_value_or_zero,
  "deposit": float_value_or_zero,
  "area_sqft": float_value_or_null
}}
Write ONLY the raw JSON object and nothing else.
"""

ESTIMATE_BENCHMARKS_PROMPT = """You are a Bangalore real estate pricing intelligence analyst.
Given a locality in Bangalore, estimate realistic market pricing benchmarks:
1. The typical average rent rate in INR per SqFt (e.g. 35.0 to 65.0).
2. A realistic standard deviation in INR per SqFt for pricing variance in this locality (usually between 4.0 and 10.0).

Locality: {locality}

Return a strictly formatted JSON object:
{{
  "avg_price_per_sqft": float_value,
  "std_price_per_sqft": float_value
}}
Write ONLY the raw JSON block. Do not wrap in markdown, backticks or formatting.
"""

VIBE_CHECK_PROMPT = """You are the "Vibe Check Agent" in a rental verification network.
Given the user's raw property description or input listing, analyze the text to find:
1. Potential discrepancy red flags (e.g., listing claiming "next to metro" but mentioning "20 minutes walk").
2. Community signals (e.g., family-focused, nightlife, noise problems, security).
3. Lifestyle/diet/pet rules (e.g., "Only pure veg", "No pets", "Tenant type: bachelor boys only").
4. Overall sentiment profile of the listing (e.g. Enthusiastic, Pressuring, Deceptive, Warm).

Raw Listing Input:
{listing_input}

Return a strictly formatted JSON object matching this schema:
{{
  "amenity_vs_claim_diffs": ["list of found discrepancies or exaggerations"],
  "community_signals": ["extracted vibe/neighbourhood feel signals from text"],
  "diet_pet_lifestyle": ["restrictive rules like food, pets, gender, marital status constraints"],
  "listing_nlp_sentiment": "One word describing overall listing sentiment"
}}
Ensure you return ONLY the raw JSON structure. Do not enclose it in markdown tables, wrappers or backticks.
"""

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

SYNTHESIS_PROMPT = """You are the "Synthesis Agent" in a rental validation multi-agent network.
Collect all preceding sub-agent analyses and synthesize them into a consolidated "Verdict Card" report.

Context data:
- Address Resolved: {address_resolved}
- Price Analysis: {pricing_data}
- Vibe & Rules: {vibe_data}
- Neighborhood & Metro proximity: {neighbourhood_data}

{critique_section}

Output parameters required:
1. Overpriced Percentage: directly mapped or adjusted from Price Analysis.
2. Red Flags list: Gather extreme prices, strict lease terms (e.g. high deposit, bachelors penalty, veg-only restrictions) or POI deficiencies (e.g. no metro within 3km).
3. Broker Questionnaire: 4 key critical/clever questions to ask the broker or owner based on discrepancies OR constraints identified here.
4. Fair Range: Return a dynamic estimates minimum and maximum rate (e.g., average rent +/- 10%).
5. Neighbourhood Score: Compute a score from 0 to 10 based on POIs (Metro < 1.5km adds 4 pts, School > 0 adds 2 pts, Hospital > 0 adds 2 pts, Market > 0 adds 2 pts).

Return a strictly formatted JSON object matching this schema:
{{
  "fair_range_min": 32000.0,
  "fair_range_max": 38000.0,
  "overpriced_percentage": 12.5,
  "red_flags": ["example flag 1", "example flag 2"],
  "neighbourhood_score": 8.0,
  "broker_questionnaire": ["question 1", "question 2"]
}}
Provide ONLY the raw JSON response.
"""
