EXTRACT_LOCALITY_PROMPT = """You are a Bangalore spatial resolver agent.
Analyze the given rental property listing content and extract:
1. The target locality or area in Bangalore (e.g. Whitefield, Koramangala, Indiranagar, HSR Layout).
2. A cleaned, structured address ending in Bangalore, Karnataka — suitable for a geocoding lookup.

Raw Listing Content:
{listing_input}
"""

EXTRACT_FINANCIALS_PROMPT = """You are a property financial extractor. Given the raw property description, extract:
1. Monthly Rent in INR.
2. Security Deposit in INR.
3. Property Area in SqFt.

Raw listing content:
{listing_input}
"""

ESTIMATE_BENCHMARKS_PROMPT = """You are a Bangalore real estate pricing intelligence analyst.
Given a locality in Bangalore, estimate realistic market pricing benchmarks:
1. The typical average rent rate in INR per SqFt (e.g. 35.0 to 65.0).
2. A realistic standard deviation in INR per SqFt for pricing variance in this locality (usually between 4.0 and 10.0).

Locality: {locality}
"""

VIBE_CHECK_PROMPT = """You are the "Vibe Check Agent" in a rental verification network.
Given the user's raw property description or input listing, analyze the text to find:
1. Potential discrepancy red flags (e.g., listing claiming "next to metro" but mentioning "20 minutes walk").
2. Community signals (e.g., family-focused, nightlife, noise problems, security).
3. Lifestyle/diet/pet rules (e.g., "Only pure veg", "No pets", "Tenant type: bachelor boys only").
4. Overall sentiment profile of the listing (e.g. Enthusiastic, Pressuring, Deceptive, Warm).

Raw Listing Input:
{listing_input}
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
4. Fair Range: Return a dynamic estimate minimum and maximum rate (e.g., average rent +/- 10%).
5. Neighbourhood Score: Compute a score from 0 to 10 based on POIs (Metro < 1.5km adds 4 pts, School > 0 adds 2 pts, Hospital > 0 adds 2 pts, Market > 0 adds 2 pts).
"""
