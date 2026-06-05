"""
rendering/ui/app.py
───────────────────
Premium Streamlit Web UI for the Rental Truth-Teller Bangalore Verification System.
"""

import os
import sys
import pandas as pd
import streamlit as st
import pydeck as pdk
import requests

# Configure root path mapping
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from config.settings import config
from config.logging_utils import setup_logging
from config.constants import SAMPLE_SCENARIOS
from agents.service import TruthTellerService
from agents.state import AddressResolved, PricingAnalysis, VibeAnalysis, NeighbourhoodAnalysis, VerdictCard

# Setup UI logging
setup_logging(log_file=config.UI_LOG_PATH, console=False)

# Set premium page config
st.set_page_config(
    page_title="⚖️ Rental Truth-Teller Dashboard",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject premium custom CSS
st.markdown("""
<style>
    .reportview-container { background: #0e1117; }
    .metric-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        transition: transform 0.3s ease;
    }
    .metric-card:hover { transform: translateY(-4px); border-color: rgba(255, 255, 255, 0.2); }
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
    .agent-node-box {
        padding: 12px 18px;
        background: rgba(255, 255, 255, 0.02);
        border-left: 4px solid #ff4b4b;
        border-radius: 0 8px 8px 0;
        margin-bottom: 12px;
    }
    .red-flag-box {
        background: rgba(255, 75, 75, 0.07);
        border: 1px solid rgba(255, 75, 75, 0.2);
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
    }
    .smart-question {
        background: rgba(0, 150, 255, 0.05);
        border: 1px solid rgba(0, 150, 255, 0.15);
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align: center; margin-bottom: 0;'>⚖️ Rental Truth-Teller</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888; font-size: 1.15rem; margin-top: 5px; margin-bottom: 30px;'>Bangalore Multi-Agent Real Estate Verification Network</p>", unsafe_allow_html=True)

# Sidebar controls
st.sidebar.markdown("### ⚙️ AI Orchestration Engine")

execution_mode = st.sidebar.radio("Execution Mode", ["Direct Service", "API Call"], index=0)

selected_provider = st.sidebar.selectbox(
    "LLM Provider Target",
    ["Gemini", "AWS Bedrock", "Mock Fallback"],
    index=0
)

provider_env_map = {"Gemini": "gemini", "AWS Bedrock": "bedrock", "Mock Fallback": "mock"}
os.environ["LLM_PROVIDER"] = provider_env_map[selected_provider]

gemini_key = st.sidebar.text_input("Gemini API Key", value=config.GEMINI_API_KEY or "", type="password")
if gemini_key: os.environ["GEMINI_API_KEY"] = gemini_key

aws_key = st.sidebar.text_input("AWS Access Key", value=config.AWS_ACCESS_KEY_ID or "", type="password")
if aws_key: os.environ["AWS_ACCESS_KEY_ID"] = aws_key

st.sidebar.markdown("---")
st.sidebar.markdown("### 🧭 Location Settings")
st.sidebar.info(f"Analyzing rental listings in Bangalore: {', '.join(config.BANGALORE_AREAS)}.")

col_left, col_right = st.columns([5, 7], gap="large")

with col_left:
    st.markdown("### 📝 Input Property Listing")
    selected_scenario = st.selectbox("Or load a test listing scenario:", list(SAMPLE_SCENARIOS.keys()))
    listing_text = st.text_area("Paste raw rental advertisement text here:", value=SAMPLE_SCENARIOS[selected_scenario], height=250)
    verify_btn = st.button("🚀 VERIFY WITH AGENT NETWORK", use_container_width=True)

with col_right:
    st.markdown("### 🗺️ Spatial POI Map & Comparables")
    map_placeholder = st.empty()
    default_map_data = pd.DataFrame({'lat': [12.9716], 'lon': [77.5946], 'name': ['Bangalore City Centre']})
    map_placeholder.map(default_map_data, zoom=11)

if verify_btn:
    if not listing_text.strip():
        st.error("Please provide a listing description to verify!")
    else:
        st.markdown("---")
        st.markdown("## 🧠 Real-Time Multi-Agent Workflow")
        
        with st.status(f"Orchestrating agent network ({execution_mode})...", expanded=True) as status:
            try:
                if execution_mode == "API Call":
                    api_url = os.environ.get("TRUTH_TELLER_API_URL", "http://localhost:8000/verify")
                    resp = requests.post(api_url, json={"text": listing_text})
                    resp.raise_for_status()
                    final_response = resp.json()
                else:
                    final_response = TruthTellerService.verify_listing(listing_text)

                status.update(label="✓ Verification completed successfully!", state="complete", expanded=False)
            except Exception as ex:
                status.update(label=f"⚠️ Error in agent execution: {ex}", state="error")
                st.exception(ex)
                st.stop()
        
        # Helper to convert dict back to object if from API
        def get_data(key, model):
            val = final_response.get(key)
            if not val: return None
            return model(**val) if isinstance(val, dict) else val

        address = get_data("address_resolved", AddressResolved)
        pricing = get_data("pricing_data", PricingAnalysis)
        vibe = get_data("vibe_data", VibeAnalysis)
        neighbourhood = get_data("neighbourhood_data", NeighbourhoodAnalysis)
        verdict = get_data("final_verdict", VerdictCard)
        
        if address:
            # Handle both object and dict access
            lat = address.geo.lat if hasattr(address.geo, 'lat') else address.geo['lat'] if address.geo else 12.9716
            lon = address.geo.lon if hasattr(address.geo, 'lon') else address.geo['lon'] if address.geo else 77.5946
            
            map_points = [{"lat": lat, "lon": lon, "name": f"Target Listing in {address.locality}", "type": "Property"}]
            if neighbourhood and neighbourhood.facilities:
                for facility in neighbourhood.facilities:
                    f_name = facility.name if hasattr(facility, 'name') else facility['name']
                    f_dist = facility.distance_km if hasattr(facility, 'distance_km') else facility['distance_km']
                    f_type = facility.facility_type if hasattr(facility, 'facility_type') else facility['facility_type']
                    
                    offset_lat = lat + (0.0025 * (hash(f_name) % 3 - 1))
                    offset_lon = lon + (0.0025 * (hash(f_name) % 4 - 1))
                    map_points.append({"lat": offset_lat, "lon": offset_lon, "name": f"{f_name} ({f_dist} km)", "type": f_type.upper()})
            df_points = pd.DataFrame(map_points)
            color_map = {"Property": [255, 75, 75, 200], "METRO": [255, 193, 7, 200], "SCHOOL": [0, 150, 255, 200], "HOSPITAL": [0, 200, 83, 200], "MARKET": [156, 39, 176, 200]}
            df_points["color"] = df_points["type"].map(lambda x: color_map.get(x, [120, 120, 120, 200]))
            
            r_map = pdk.Deck(
                layers=[pdk.Layer("ScatterplotLayer", df_points, get_position="[lon, lat]", get_color="color", get_radius=120, pickable=True)],
                initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=14, pitch=30),
                tooltip={"html": "<b>{name}</b><br/>Type: {type}"},
                map_style="mapbox://styles/mapbox/dark-v9"
            )
            map_placeholder.pydeck_chart(r_map)
        
        col_logs, col_trace = st.columns([6, 6])
        with col_logs:
            st.markdown("#### ⚡ Multi-Agent Step Trace")
            for msg in final_response.get("messages", []):
                st.markdown(f"<div class='agent-node-box'>{msg}</div>", unsafe_allow_html=True)
        
        with col_trace:
            st.markdown("#### 🎨 Listing Vibe, Diet & Rules")
            if vibe:
                st.markdown(f"**NLP Sentiment Profile:** `{vibe.listing_nlp_sentiment}`")
                if vibe.diet_pet_lifestyle:
                    for r in vibe.diet_pet_lifestyle: st.markdown(f"- 🚫 {r}")
                if vibe.amenity_vs_claim_diffs:
                    for d in vibe.amenity_vs_claim_diffs: st.markdown(f"- ⚠️ {d}")

        st.markdown("---")
        st.markdown("## 🏆 Unified Verdict Card Report")
        if verdict:
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            
            with m_col1:
                st.markdown(f"<div class='metric-card'><p style='color: #888; margin: 0;'>⚖️ Fair Rental Range</p><p class='metric-value-green'>₹{int(verdict.fair_range_min):,} - ₹{int(verdict.fair_range_max):,}</p></div>", unsafe_allow_html=True)
            with m_col2:
                st.markdown(f"<div class='metric-card'><p style='color: #888; margin: 0;'>🪙 Price Deviation</p><p class='metric-value'>{verdict.overpriced_percentage:.1f}%</p></div>", unsafe_allow_html=True)
            with m_col3:
                st.markdown(f"<div class='metric-card'><p style='color: #888; margin: 0;'>💰 Upfront Cost</p><p class='metric-value'>₹{int(verdict.total_upfront_cost):,}</p></div>", unsafe_allow_html=True)
            with m_col4:
                st.markdown(f"<div class='metric-card'><p style='color: #888; margin: 0;'>🏫 Neighborhood Score</p><p class='metric-value-green'>{verdict.neighbourhood_score:.1f} / 10</p></div>", unsafe_allow_html=True)

            col_details_l, col_details_r = st.columns([6, 6], gap="large")
            with col_details_l:
                st.markdown("### 🚨 Verified Red Flags")
                if verdict.red_flags:
                    for flag in verdict.red_flags: st.markdown(f"<div class='red-flag-box'>⚠️ {flag}</div>", unsafe_allow_html=True)
                st.markdown("### 💬 Ask-The-Broker")
                if verdict.broker_questionnaire:
                    for q in verdict.broker_questionnaire: st.markdown(f"<div class='smart-question'>{q}</div>", unsafe_allow_html=True)

            with col_details_r:
                st.markdown(f"**Target Locality:** `{address.locality if address else 'Bangalore'}`")
                if neighbourhood and neighbourhood.facilities:
                    for facility in neighbourhood.facilities:
                        f_name = facility.name if hasattr(facility, 'name') else facility['name']
                        f_dist = facility.distance_km if hasattr(facility, 'distance_km') else facility['distance_km']
                        f_type = facility.facility_type if hasattr(facility, 'facility_type') else facility['facility_type']
                        st.markdown(f"• **[{f_type.upper()}]** {f_name} ({f_dist} km)")
