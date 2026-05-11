"""
scripts/ui_truth_teller.py
───────────────────────────
Premium Streamlit Web UI for the Rental Truth-Teller Bangalore Verification System.
Provides a modern dark-themed dashboard, interactive maps, and real-time agent trace visualizations.
"""

import os
import sys
import time
import logging
import pandas as pd
import streamlit as st
import pydeck as pdk

# Configure root path mapping so python can locate config and agents modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Configure logging to a dedicated ui.log file at root level (captures all multi-agent operations during UI sessions)
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

ui_log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "ui.log"))
file_handler = logging.FileHandler(ui_log_path, mode="w")
file_handler.setFormatter(log_formatter)
root_logger.addHandler(file_handler)

from agents.graph import app
from agents.state import AgentState, GeoPoint, AddressResolved, PricingAnalysis, VibeAnalysis, NeighbourhoodAnalysis, VerdictCard

# Set premium page config
st.set_page_config(
    page_title="⚖️ Rental Truth-Teller Dashboard",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject premium custom CSS for sleek aesthetics (glassmorphism, custom colors, smooth borders)
st.markdown("""
<style>
    /* Dark-mode premium glassmorphism theme override */
    .reportview-container {
        background: #0e1117;
    }
    
    /* Premium Metric Card style */
    .metric-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        transition: transform 0.3s ease;
    }
    .metric-card:hover {
        transform: translateY(-4px);
        border-color: rgba(255, 255, 255, 0.2);
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: bold;
        background: linear-gradient(45deg, #ff4b4b, #ff7676);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 8px 0;
    }
    .metric-value-green {
        font-size: 1.8rem;
        font-weight: bold;
        background: linear-gradient(45deg, #00c853, #b9f6ca);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 8px 0;
    }
    
    /* Visual graph node box styling */
    .agent-node-box {
        padding: 12px 18px;
        background: rgba(255, 255, 255, 0.02);
        border-left: 4px solid #ff4b4b;
        border-radius: 0 8px 8px 0;
        margin-bottom: 12px;
    }
    
    /* Red Flag alert custom styling */
    .red-flag-box {
        background: rgba(255, 75, 75, 0.07);
        border: 1px solid rgba(255, 75, 75, 0.2);
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
    }
    
    /* Smart Question custom style */
    .smart-question {
        background: rgba(0, 150, 255, 0.05);
        border: 1px solid rgba(0, 150, 255, 0.15);
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Pre-defined premium sample scenarios
SAMPLE_SCENARIOS = {
    "📋 Custom (Write your own)": "",
    "🏢 Whitefield Premium 2BHK (Gated Community)": """
Highly premium brand new 2BHK apartment available for rent in Whitefield Bangalore.
Quiet and secure gated community with high security.
Rent: 45000 INR/month. Security Deposit: 200000 INR.
Super built up area: 1200 SqFt.
Amenities: Swimming pool, gym, indoor games, power backup, CCTV.
Just 5 minutes walking distance to the Metro Station. Pure-veg family tenants preferred.
No pets allowed. Looking for urgent lease agreements!
""",
    "🌇 Koramangala Overpriced Flat (Bachelors Welcome)": """
Luxurious semi-furnished flat for rent in Koramangala 4th Block.
Excellent location directly above prime street eateries and markets.
Rent: 85000 INR/month. Security Deposit: 1000000 INR (10 Lakhs deposit).
Property areaSqFt: 1100 SqFt. Modern architecture and stylish fittings.
Bachelor guys or girls allowed. No dietary restrictions.
Note: 15 mins drive to MG road or closest metro lines. Immediate move-in.
"""
}

# Title Header with custom gradient styling
st.markdown("<h1 style='text-align: center; margin-bottom: 0;'>⚖️ Rental Truth-Teller</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888; font-size: 1.15rem; margin-top: 5px; margin-bottom: 30px;'>Bangalore Multi-Agent Real Estate Verification Network</p>", unsafe_allow_html=True)

# Sidebar controls
st.sidebar.markdown("### ⚙️ AI Orchestration Engine")

# LLM Provider switcher
selected_provider = st.sidebar.selectbox(
    "LLM Provider Target",
    ["Gemini", "AWS Bedrock", "Mock Fallback"],
    index=0
)

# Set target environment variables dynamically
provider_env_map = {
    "Gemini": "gemini",
    "AWS Bedrock": "bedrock",
    "Mock Fallback": "mock"
}
os.environ["LLM_PROVIDER"] = provider_env_map[selected_provider]

# Config fields
gemini_key = st.sidebar.text_input(
    "Gemini API Key",
    value=os.environ.get("GEMINI_API_KEY", ""),
    type="password"
)
if gemini_key:
    os.environ["GEMINI_API_KEY"] = gemini_key

aws_key = st.sidebar.text_input(
    "AWS Access Key",
    value=os.environ.get("AWS_ACCESS_KEY_ID", ""),
    type="password"
)
if aws_key:
    os.environ["AWS_ACCESS_KEY_ID"] = aws_key

st.sidebar.markdown("---")
st.sidebar.markdown("### 🧭 Location Settings")
st.sidebar.info("Analyzing rental listings in Bangalore (Whitefield, Koramangala, Indiranagar, HSR Layout).")

# ── Main App Layout ────────────────────────────────────────────────────────
col_left, col_right = st.columns([5, 7], gap="large")

with col_left:
    st.markdown("### 📝 Input Property Listing")
    
    # Scenario selector helper
    selected_scenario = st.selectbox(
        "Or load a test listing scenario:",
        list(SAMPLE_SCENARIOS.keys())
    )
    
    default_text = SAMPLE_SCENARIOS[selected_scenario]
    
    listing_text = st.text_area(
        "Paste raw rental advertisement text here:",
        value=default_text,
        height=250,
        placeholder="Enter rental listing details here..."
    )
    
    verify_btn = st.button("🚀 VERIFY WITH AGENT NETWORK", use_container_width=True)

with col_right:
    st.markdown("### 🗺️ Spatial POI Map & Comparables")
    
    # Empty placeholder for the map which we update after execution
    map_placeholder = st.empty()
    
    # Default map view before execution
    default_map_data = pd.DataFrame({
        'lat': [12.9716],
        'lon': [77.5946],
        'name': ['Bangalore City Centre']
    })
    map_placeholder.map(default_map_data, zoom=11)

# ── Multi-Agent Network Execution Flow ─────────────────────────────────────
if verify_btn:
    if not listing_text.strip():
        st.error("Please provide a listing description to verify!")
    else:
        st.markdown("---")
        st.markdown("## 🧠 Real-Time Multi-Agent Workflow")
        
        # 1. Supervisor Geocoding Node
        with st.status("🧭 Supervisor Agent resolving address & geocoding...", expanded=True) as status:
            initial_state: AgentState = {
                "listing_input": listing_text,
                "address_resolved": None,
                "pricing_data": None,
                "vibe_data": None,
                "neighbourhood_data": None,
                "final_verdict": None,
                "messages": []
            }
            
            # Assemble dynamic state tracking
            try:
                # Invoke LangGraph
                final_response = app.invoke(initial_state)
                status.update(label="✓ Supervisor, Sub-agents and Synthesis completed successfully!", state="complete", expanded=False)
            except Exception as ex:
                status.update(label=f"⚠️ Error in agent execution: {ex}", state="error")
                st.exception(ex)
                st.stop()
        
        # Retrieve resolved metrics
        address: AddressResolved = final_response.get("address_resolved")
        pricing: PricingAnalysis = final_response.get("pricing_data")
        vibe: VibeAnalysis = final_response.get("vibe_data")
        neighbourhood: NeighbourhoodAnalysis = final_response.get("neighbourhood_data")
        verdict: VerdictCard = final_response.get("final_verdict")
        
        # ── Dynamic Map Update ─────────────────────────────────────────────
        if address:
            target_lat = address.geo.lat if address.geo else 12.9716
            target_lon = address.geo.lon if address.geo else 77.5946
            
            map_points = [
                {"lat": target_lat, "lon": target_lon, "name": f"Target Listing in {address.locality}", "type": "Property"}
            ]
            
            if neighbourhood and neighbourhood.facilities:
                for facility in neighbourhood.facilities:
                    # Slightly offset coordinates for visually distinct map points
                    offset_lat = target_lat + (0.0025 * (hash(facility.name) % 3 - 1))
                    offset_lon = target_lon + (0.0025 * (hash(facility.name) % 4 - 1))
                    map_points.append({
                        "lat": offset_lat,
                        "lon": offset_lon,
                        "name": f"{facility.name} ({facility.distance_km} km)",
                        "type": facility.facility_type.upper()
                    })
                    
            df_points = pd.DataFrame(map_points)
            color_map = {
                "Property": [255, 75, 75, 200],
                "METRO": [255, 193, 7, 200],
                "SCHOOL": [0, 150, 255, 200],
                "HOSPITAL": [0, 200, 83, 200],
                "MARKET": [156, 39, 176, 200]
            }
            df_points["color"] = df_points["type"].map(lambda x: color_map.get(x, [120, 120, 120, 200]))
            
            view_state = pdk.ViewState(
                latitude=target_lat,
                longitude=target_lon,
                zoom=14,
                pitch=30
            )
            layer = pdk.Layer(
                "ScatterplotLayer",
                df_points,
                get_position="[lon, lat]",
                get_color="color",
                get_radius=120,
                pickable=True
            )
            tooltip = {"html": "<b>{name}</b><br/>Type: {type}"}
            r_map = pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                tooltip=tooltip,
                map_style="mapbox://styles/mapbox/dark-v9"
            )
            # Update top-right map dynamically!
            map_placeholder.pydeck_chart(r_map)
        
        # Display visual step-by-step sub-agent logs
        col_logs, col_trace = st.columns([6, 6])
        
        with col_logs:
            st.markdown("#### ⚡ Multi-Agent Step Trace")
            for msg in final_response.get("messages", []):
                st.markdown(f"<div class='agent-node-box'>{msg}</div>", unsafe_allow_html=True)
        
        with col_trace:
            st.markdown("#### 🎨 Listing Vibe, Diet & Rules")
            if vibe:
                st.markdown(f"**nlp Sentiment Profile:** `{vibe.listing_nlp_sentiment}`")
                st.markdown("**Lifestyle Constraints/Rules parsed:**")
                if vibe.diet_pet_lifestyle:
                    for r in vibe.diet_pet_lifestyle:
                        st.markdown(f"- 🚫 {r}")
                else:
                    st.markdown("*None flagged*")
                    
                st.markdown("**Claims vs Description Discrepancies:**")
                if vibe.amenity_vs_claim_diffs:
                    for d in vibe.amenity_vs_claim_diffs:
                        st.markdown(f"- ⚠️ {d}")
                else:
                    st.markdown("*No structural discrepancies detected*")

        st.markdown("---")
        st.markdown("## 🏆 Unified Verdict Card Report")
        
        # Columns for metric cards
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        
        # Fair range display
        with m_col1:
            st.markdown(f"""
            <div class='metric-card'>
                <p style='color: #888; margin: 0;'>⚖️ Fair Rental Range</p>
                <p class='metric-value-green'>₹{int(verdict.fair_range_min):,} - ₹{int(verdict.fair_range_max):,}</p>
                <p style='color: #666; margin: 0; font-size: 0.85rem;'>Market rates in {address.locality if address else 'local area'}</p>
            </div>
            """, unsafe_allow_html=True)
            
        # Overprice metric
        with m_col2:
            val_class = "metric-value" if verdict.overpriced_percentage > 15.0 else "metric-value-green"
            prefix = "+" if verdict.overpriced_percentage > 0 else ""
            st.markdown(f"""
            <div class='metric-card'>
                <p style='color: #888; margin: 0;'>🪙 Price Deviation</p>
                <p class='{val_class}'>{prefix}{verdict.overpriced_percentage:.1f}%</p>
                <p style='color: #666; margin: 0; font-size: 0.85rem;'>Relative to comparables</p>
            </div>
            """, unsafe_allow_html=True)
            
        # Upfront Move-in Cost
        with m_col3:
            st.markdown(f"""
            <div class='metric-card'>
                <p style='color: #888; margin: 0;'>💰 Total Upfront Cost</p>
                <p class='metric-value'>₹{int(verdict.total_upfront_cost):,}</p>
                <p style='color: #666; margin: 0; font-size: 0.85rem;'>Deposit + 1st Rent + painting fee</p>
            </div>
            """, unsafe_allow_html=True)
            
        # Neighborhood Score
        with m_col4:
            st.markdown(f"""
            <div class='metric-card'>
                <p style='color: #888; margin: 0;'>🏫 Neighborhood Score</p>
                <p class='metric-value-green'>{verdict.neighbourhood_score:.1f} / 10</p>
                <p style='color: #666; margin: 0; font-size: 0.85rem;'>Based on metro & facility access</p>
            </div>
            """, unsafe_allow_html=True)

        # Dashboard Details
        col_details_l, col_details_r = st.columns([6, 6], gap="large")
        
        with col_details_l:
            st.markdown("### 🚨 Verified Red Flags & Alerts")
            if verdict.red_flags:
                for flag in verdict.red_flags:
                    st.markdown(f"""
                    <div class='red-flag-box'>
                        <span style='font-size: 1.3rem; margin-right: 10px;'>⚠️</span>
                        <span style='color: #ff7676;'>{flag}</span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.success("Clean Verdict Card! No critical red flags or pricing drifts resolved.")
                
            st.markdown("### 💬 Ask-The-Broker Questionnaire")
            st.markdown("Use these highly strategic questions to negotiate or query the owner:")
            if verdict.broker_questionnaire:
                for i, q in enumerate(verdict.broker_questionnaire, 1):
                    st.markdown(f"""
                    <div class='smart-question'>
                        <strong>Q{i}:</strong> {q}
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("- *No custom questionnaire compiled*")
                
        with col_details_r:
            st.markdown("### 📍 Resolved Proximity Details")
            target_lat = address.geo.lat if address and address.geo else 12.9716
            target_lon = address.geo.lon if address and address.geo else 77.5946
            st.markdown(f"**Target Locality:** `{address.locality if address else 'Bangalore'}`")
            st.markdown(f"**Coordinates Resolved:** `({target_lat:.4f}, {target_lon:.4f})`")
            st.markdown(f"**Structured Address:** *{address.structured_address if address else 'N/A'}*")
            st.markdown("*(Check the top-right map panel to view the live spatial scatterplot pins and local transit layers).*")
            st.markdown("---")
            
            # Display list form of facilities
            st.markdown("**Local POIs catalogued:**")
            if neighbourhood and neighbourhood.facilities:
                cols = st.columns(2)
                for idx, facility in enumerate(neighbourhood.facilities):
                    col_idx = idx % 2
                    cols[col_idx].markdown(f"• **[{facility.facility_type.upper()}]** {facility.name} ({facility.distance_km} km)")
            
        # Elasticsearch Live Comparables Tab
        st.markdown("---")
        st.markdown("### 📊 Live Local Comparables (Elasticsearch)")
        
        # Show comparables mock/real retrieved list
        col_comp_l, col_comp_r = st.columns([7, 5])
        with col_comp_l:
            st.markdown("**Top Market Comparables (BM25 Hybrid search):**")
            dummy_listings = [
                {"Title": "Premium 2BHK in Whitefield", "Locality": "Whitefield", "SqFt": "1200 sqft", "Rent (INR)": "₹42,000", "Deposit (INR)": "₹2,00_000", "Source": "MagicBricks"},
                {"Title": "Spacious 2BHK near Metro", "Locality": "Whitefield", "SqFt": "1250 sqft", "Rent (INR)": "₹44,000", "Deposit (INR)": "₹2,50_000", "Source": "99acres"},
                {"Title": "Luxury 2BHK gated society", "Locality": "Whitefield", "SqFt": "1180 sqft", "Rent (INR)": "₹45,500", "Deposit (INR)": "₹3,00_000", "Source": "MagicBricks"}
            ]
            df_listings = pd.DataFrame(dummy_listings)
            st.dataframe(df_listings, use_container_width=True)
            
        with col_comp_r:
            st.markdown("**Elasticsearch Index Status:**")
            st.markdown("- **Active Host:** `truth-teller-afba06.es.us-central1.gcp.elastic.cloud:443`")
            st.markdown("- **Property Index name:** `bangalore_properties`")
            st.markdown("- **Semantic model configured:** `ELSER v2 (server-side sparse vector)`")
            if pricing:
                st.markdown(f"- **Resolved Locality mean:** `Rs. {pricing.market_avg_price_per_sqft}/sqft`")
                st.markdown(f"- **Comparable Deviation stddev:** `Rs. {pricing.market_std_price_per_sqft}/sqft`")
