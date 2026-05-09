"""
agents/pricing.py
─────────────────
Pricing Agent: Performs market rate checks, deposit evaluations, and flags price drift
using hybrid Elasticsearch search.
"""

from __future__ import annotations

import json
import logging
import math
from langchain_core.prompts import ChatPromptTemplate
from agents.config import get_llm, get_elasticsearch_client
from agents.state import AgentState, PricingAnalysis

log = logging.getLogger(__name__)

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

def pricing_node(state: AgentState) -> dict:
    log.info("[Pricing Agent] Analyzing Pricing, Deposit Norms, & Price Drift…")
    
    listing_input = state.get("listing_input", "")
    address_resolved = state.get("address_resolved")
    
    if not listing_input:
        return {"pricing_data": PricingAnalysis()}

    # 1. Parse client-side listing financials using LLM
    llm = get_llm(temperature=0.1)
    prompt = ChatPromptTemplate.from_template(EXTRACT_FINANCIALS_PROMPT)
    chain = prompt | llm
    
    curr_rent = 0.0
    curr_deposit = 0.0
    curr_area = None
    
    try:
        response = chain.invoke({"listing_input": listing_input})
        content = response.content.strip()
        if content.startswith("```json"):
            content = content.replace("```json", "", 1)
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()
        
        financials = json.loads(content)
        curr_rent = float(financials.get("rent", 0.0))
        curr_deposit = float(financials.get("deposit", 0.0))
        curr_area = financials.get("area_sqft")
        if curr_area is not None:
            curr_area = float(curr_area)
    except Exception as e:
        log.error(f"[Pricing Agent] Financial extraction parsing exception: {e}")

    # 2. Local market benchmarks by region (Used as fallback if ES contains no comparables or is empty)
    locality = address_resolved.locality if address_resolved else ""
    if not locality and address_resolved:
        locality = address_resolved.structured_address.split(",")[0]
        
    # Default Bangalore rates by area (per sqft in INR)
    default_avg_map = {
        "whitefield": {"avg": 35.0, "std": 6.0},
        "koramangala": {"avg": 52.0, "std": 8.0},
        "indiranagar": {"avg": 58.0, "std": 9.5},
        "bellandur": {"avg": 39.0, "std": 5.5},
        "hsr": {"avg": 42.0, "std": 7.0},
    }
    
    norm_key = locality.lower().strip() if locality else ""
    market_avg = 40.0
    market_std = 7.0
    for key, val in default_avg_map.items():
        if key in norm_key:
            market_avg = val["avg"]
            market_std = val["std"]
            break

    # 3. Query Elasticsearch for actual listing comparables
    es_ratings = []
    try:
        es = get_elasticsearch_client()
        # Query matching properties within the locality using fuzzy or keyword
        search_body = {
            "query": {
                "bool": {
                    "must": [
                        {"match": {"transaction_type": "rent"}},
                    ],
                    "should": [
                        {"match": {"area": locality if locality else "Bangalore"}},
                        {"match": {"address": locality if locality else "Bangalore"}}
                    ]
                }
            },
            "size": 20
        }
        
        res = es.search(index="bangalore_properties", body=search_body)
        hits = res.get("hits", {}).get("hits", [])
        
        for hit in hits:
            source_doc = hit.get("_source", {})
            rent = source_doc.get("price")
            sqft = source_doc.get("area_sqft")
            if rent and sqft:
                es_ratings.append(float(rent) / float(sqft))
                
        if len(es_ratings) > 2:
            # Calculate actual elasticsearch comparables mean and stddev
            market_avg = sum(es_ratings) / len(es_ratings)
            variance = sum((x - market_avg) ** 2 for x in es_ratings) / len(es_ratings)
            market_std = math.sqrt(variance) if variance > 0 else 1.0
            log.info(f"[Pricing Agent] ES search matched {len(es_ratings)} comparables. Calculated Mean Rate: Rs.{market_avg:.2f}/sqft, StdDev: {market_std:.2f}")
        else:
            log.info(f"[Pricing Agent] Insufficient ES comparables found ({len(es_ratings)}). Using region-based fallback metrics for `{locality}` (Avg: Rs.{market_avg}/sqft).")

    except Exception as exc:
        log.warning(f"[Pricing Agent] Elasticsearch connection was bypassed or failed: {exc}. Using generic regional benchmarks.")

    # 4. Process pricing parameters
    curr_price_per_sqft = None
    overpriced_pct = 0.0
    price_drift = False
    
    if curr_area and curr_area > 0 and curr_rent > 0:
        curr_price_per_sqft = curr_rent / curr_area
        overpriced_pct = ((curr_price_per_sqft - market_avg) / market_avg) * 100.0
        # Price drift logic: Let's flag if rate exceeds average + 1.5 * stddev
        if curr_price_per_sqft > (market_avg + 1.5 * market_std):
            price_drift = True

    # 5. Deposit Multiplier validation (standard in Bangalore is 5 to 10 months rent)
    deposit_mult = 0.0
    deposit_normal = True
    if curr_rent > 0:
        deposit_mult = curr_deposit / curr_rent
        # Flag anormal if deposit represents > 10 months of rent
        if deposit_mult > 10.0:
            deposit_normal = False
            
    analysis_res = PricingAnalysis(
        rent_amount=curr_rent,
        deposit_amount=curr_deposit,
        deposit_multiplier=round(deposit_mult, 2),
        deposit_is_normal=deposit_normal,
        area_sqft=curr_area,
        price_per_sqft=round(curr_price_per_sqft, 2) if curr_price_per_sqft else None,
        market_avg_price_per_sqft=round(market_avg, 2),
        market_std_price_per_sqft=round(market_std, 2),
        overpriced_percentage=round(overpriced_pct, 1),
        price_drift_flag=price_drift
    )
    
    msg = f"[Pricing Agent] Completed. Rent: Rs.{curr_rent:.0f}, Security Dep: {deposit_mult:.1f}x Rent multiplier."
    log.info(msg)
    return {
        "pricing_data": analysis_res,
        "messages": [msg]
    }
