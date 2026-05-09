"""
scripts/run_truth_teller.py
───────────────────────────
CLI entrypoint script to test the compiled multi-agent Graph.
Executes sample rental listings in Bangalore and showcases the compiled Verdict Card.
"""

from __future__ import annotations

import logging
import os
import sys

# Configure root path mapping so python can locate config and agents modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configure dual logging to both console and a dedicated backend.log file
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Console Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

# Dedicated Backend File Handler
backend_log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend.log"))
file_handler = logging.FileHandler(backend_log_path, mode="w")
file_handler.setFormatter(log_formatter)
root_logger.addHandler(file_handler)

log = logging.getLogger("RunTruthTeller")

from agents.graph import app
from agents.state import AgentState

# Ensure we mock Bedrock/Claude if direct AWS keys are missing or placeholders so testing is flawless
aws_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
if not aws_key or aws_key.startswith("BedrockAPIKey") or os.environ.get("USE_MOCK_LLM") == "true":
    log.info("Setting USE_MOCK_LLM = 'true' for local integration validation.")
    os.environ["USE_MOCK_LLM"] = "true"


SAMPLE_WHITEFIELD = """
Highly premium brand new 2BHK apartment available for rent in Whitefield Bangalore.
Quiet and secure gated community with high security.
Rent: 45000 INR/month. Security Deposit: 200000 INR.
Super built up area: 1200 SqFt.
Amenities: Swimming pool, gym, indoor games, power backup, CCTV.
Just 5 minutes walking distance to the Metro Station. Pure-veg family tenants preferred.
No pets allowed. Looking for urgent lease agreements!
"""

SAMPLE_KORAMANGALA_OVERPRICED = """
Luxurious semi-furnished flat for rent in Koramangala 4th Block.
Excellent location directly above prime street eateries and markets.
Rent: 85000 INR/month. Security Deposit: 1000000 INR (10 Lakhs deposit).
Property areaSqFt: 1100 SqFt. Modern architecture and stylish fittings.
Bachelor guys or girls allowed. No dietary restrictions.
Note: 15 mins drive to MG road or closest metro lines. Immediate move-in.
"""

def run_test_listing(sample_text: str, label: str):
    print("\n" + "="*80)
    print(f" RUNNING MULTI-AGENT VERIFICATION ON: {label}")
    print("="*80)
    print(f"Listing Input Snippet:\n{sample_text.strip()[:250]}...\n")
    
    initial_state: AgentState = {
        "listing_input": sample_text,
        "address_resolved": None,
        "pricing_data": None,
        "vibe_data": None,
        "neighbourhood_data": None,
        "final_verdict": None,
        "messages": []
    }
    
    try:
        # Invoke the compiled StateGraph
        final_response = app.invoke(initial_state)
        
        print("\n"+"-"*40 + " AGENT TRACE LOGGER " + "-"*40)
        for msg in final_response.get("messages", []):
            print(f" > {msg}")
        print("-"*100)
        
        address = final_response.get("address_resolved")
        pricing = final_response.get("pricing_data")
        vibe = final_response.get("vibe_data")
        neighbourhood = final_response.get("neighbourhood_data")
        verdict = final_response.get("final_verdict")
        
        if address:
            print(f"\n🧭 Geocoding Result: {address.locality} | Coords: ({address.geo.lat}, {address.geo.lon})")
            print(f"   Structured Address: {address.structured_address}")
            
        if pricing:
            print(f"\n🪙 Pricing details: Rent: Rs.{pricing.rent_amount:.2f} | Deposit: Rs.{pricing.deposit_amount:.2f} ({pricing.deposit_multiplier}x rent)")
            print(f"   Calculated Price/Sqft: Rs.{pricing.price_per_sqft}/sqft vs Area Market Average: Rs.{pricing.market_avg_price_per_sqft}/sqft")
            print(f"   Overpriced Percentage: {pricing.overpriced_percentage}%  (Price Drift Flag: {pricing.price_drift_flag})")
            
        if vibe:
            print(f"\n🎨 Vibe Sentiment: {vibe.listing_nlp_sentiment}")
            print(f"   Lifestyle rules parsed: {vibe.diet_pet_lifestyle}")
            print(f"   Description NLP Discrepancies: {vibe.amenity_vs_claim_diffs}")
            
        if neighbourhood:
            print(f"\n🏫 POI Distance Audits:")
            for facility in neighbourhood.facilities:
                print(f"   • [{facility.facility_type.upper()}] {facility.name} at {facility.distance_km} km")
                
        if verdict:
            print("\n" + "#"*80)
            print("                   🏆 FINAL VERDICT CARD REPORT 🏆                   ")
            print("#"*80)
            print(f" ➡️ Fair Area Price Range: Rs.{verdict.fair_range_min:.1f} - Rs.{verdict.fair_range_max:.1f}")
            print(f" ➡️ Overpriced metric: {verdict.overpriced_percentage}%")
            print(f" ➡️ Expected Upfront Move-In Cost: Rs.{verdict.total_upfront_cost:.2f} (Deposit + First Rent + Standard painting/brokerage)")
            print(f" ➡️ Neighbourhood Access Score: {verdict.neighbourhood_score}/10")
            print(f" ➡️ Identified Red Flags:")
            for flag in verdict.red_flags:
                print(f"     ⚠️ {flag}")
            print(f" ➡️ Ask-The-Broker Questionnaire (Smart Questions):")
            for i, q in enumerate(verdict.broker_questionnaire or [], 1):
                print(f"     {i}. {q}")
            print("#"*80)
            
    except Exception as exc:
        log.exception(f"Validation failed for {label}: {exc}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Multi-Agent Verification on Bangalore Rental Listings.")
    parser.add_argument(
        "--listing",
        type=str,
        help="Raw listing text to verify."
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Path to file containing listing text."
    )
    
    args = parser.parse_args()
    
    if args.listing:
        run_test_listing(args.listing, "USER CUSTOM CLI LISTING")
    elif args.file:
        abs_file_path = os.path.abspath(args.file)
        if not os.path.exists(abs_file_path):
            print(f"Error: Listing file not found at {abs_file_path}")
            sys.exit(1)
        with open(abs_file_path, "r", encoding="utf-8") as f:
            file_content = f.read()
        run_test_listing(file_content, f"USER CUSTOM FILE: {os.path.basename(args.file)}")
    else:
        print("Starting multi-agent Rental Truth-Teller validation scenario (default targets)...")
        run_test_listing(SAMPLE_WHITEFIELD, "WHITEFIELD 2BHK RENTAL")
        run_test_listing(SAMPLE_KORAMANGALA_OVERPRICED, "KORAMANGALA LUXURY DECEPTIVE")
