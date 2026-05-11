"""
agents/config.py
────────────────
Initializes shared external clients (Elasticsearch, Bedrock Claude) with fallback/mocking support.
"""

from __future__ import annotations

import logging
import os
from elasticsearch import Elasticsearch
from langchain_aws import ChatBedrock
from langchain_core.language_models.chat_models import BaseChatModel

from config.settings import config as global_config

log = logging.getLogger(__name__)

from langchain_core.outputs import ChatResult

def get_response_text(response) -> str:
    """Extracts string text safely from response content, handling both string and list formats."""
    content = response.content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
            elif hasattr(part, "text"):
                parts.append(part.text)
        return "".join(parts).strip()
    return str(content).strip()


class ResilientChatModel(BaseChatModel):
    real_model: BaseChatModel
    mock_model: BaseChatModel
    use_mock: bool = False

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        # Log the raw prompt/request messages dynamically
        prompt_str = ""
        for m in messages:
            role = m.type.upper() if hasattr(m, "type") else "USER"
            prompt_str += f"\n--- {role} MESSAGE ---\n{m.content}\n"
        log.info(f"[LLM Request Prompt]:{prompt_str}")

        if self.use_mock:
            res = self.mock_model._generate(messages, stop, run_manager, **kwargs)
            try:
                log.info(f"[Mock LLM Response Content]:\n{res.generations[0].text}")
            except Exception:
                pass
            return res
        try:
            res = self.real_model._generate(messages, stop, run_manager, **kwargs)
            try:
                log.info(f"[Actual LLM Response Content]:\n{res.generations[0].text}")
            except Exception:
                pass
            return res
        except Exception as e:
            log.error(f"LLM runtime invocation failed: {e}. Automatically falling back to MockChatModel for execution.")
            self.use_mock = True
            res = self.mock_model._generate(messages, stop, run_manager, **kwargs)
            try:
                log.info(f"[Mock Fallback LLM Response Content]:\n{res.generations[0].text}")
            except Exception:
                pass
            return res

    @property
    def _llm_type(self) -> str:
        return "resilient-chat-model"

# ── LLM Client Initialization (Gemini + Bedrock + Fallback Mock) ────────────────
def get_llm(temperature: float = 0.1) -> BaseChatModel:
    """
    Returns the configured LLM Chat Model (Gemini or AWS Bedrock Claude).
    Falls back to a high-fidelity MockChatModel if credentials are missing or LLM_PROVIDER is 'mock'.
    """
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower().strip()
    aws_region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    
    # Check credentials
    has_gemini_creds = bool(os.environ.get("GEMINI_API_KEY"))
    
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    has_aws_creds = (
        aws_key != "" or 
        os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI") is not None or
        os.environ.get("AWS_BEARER_TOKEN_BEDROCK") is not None
    )
    
    use_mock = False
    if provider == "mock":
        use_mock = True
    elif provider == "gemini":
        if not has_gemini_creds:
            log.warning("LLM_PROVIDER is set to 'gemini' but GEMINI_API_KEY is missing. Falling back to MockChatModel.")
            use_mock = True
    elif provider == "bedrock":
        if not has_aws_creds:
            log.warning("LLM_PROVIDER is set to 'bedrock' but AWS credentials are missing. Falling back to MockChatModel.")
            use_mock = True
    else:
        log.warning(f"Unknown LLM_PROVIDER '{provider}'. Defaulting to MockChatModel.")
        use_mock = True

    from langchain_core.language_models.chat_models import SimpleChatModel
    from langchain_core.messages import BaseMessage, AIMessage

    class MockChatModel(SimpleChatModel):
        def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
            import json
            import re
            last_msg = messages[-1].content
            log.info(f"[MockChatModel Received]: {last_msg}")
            
            # 1. Synthesis Agent compilation
            if "synthesis agent" in last_msg.lower() or "verdict card" in last_msg.lower():
                loc = "Whitefield"
                if "koramangala" in last_msg.lower():
                    loc = "Koramangala"
                elif "indiranagar" in last_msg.lower():
                    loc = "Indiranagar"
                elif "domlur" in last_msg.lower():
                    loc = "Domlur"
                elif "hsr" in last_msg.lower():
                    loc = "HSR Layout"

                import re
                # Isolate - Price Analysis line to avoid schema example collisions
                pricing_line = ""
                for line in last_msg.splitlines():
                    if "- price analysis:" in line.lower():
                        pricing_line = line
                        break

                rent = 35000.0
                rent_match = re.search(r"rent_amount[=:\"'\s]+([\d.]+)", pricing_line)
                if rent_match:
                    rent = float(rent_match.group(1))

                overpriced = 0.0
                pct_match = re.search(r"overpriced_percentage[=:\"'\s]+([\d.-]+)", pricing_line)
                if pct_match:
                    overpriced = float(pct_match.group(1))

                market_avg = 40.0
                avg_match = re.search(r"market_avg_price_per_sqft[=:\"'\s]+([\d.]+)", pricing_line)
                if avg_match:
                    market_avg = float(avg_match.group(1))
                
                area_sqft = 1200.0
                area_match = re.search(r"area_sqft[=:\"'\s]+([\d.]+)", pricing_line)
                if area_match:
                    area_sqft = float(area_match.group(1))
                
                fair_rent_avg = market_avg * area_sqft
                fair_range_min = round(fair_rent_avg * 0.9, 1)
                fair_range_max = round(fair_rent_avg * 1.1, 1)

                red_flags = []
                if overpriced > 30.0:
                    red_flags.append(f"Property pricing is majorly drifted relative to local average benchmarks in {loc} ({overpriced:.1f}% overpriced).")
                elif overpriced < -10.0:
                    red_flags.append(f"Good deal alert: Price is {abs(overpriced):.1f}% below average comparables in {loc}.")

                # Vegetarian preferences
                if loc == "Koramangala":
                    red_flags.append("Koramangala has highly restrictive vegetarian-only preferences, which may limit occupancy options.")
                elif "veg" in last_msg.lower():
                    red_flags.append(f"Vegetarian-only preference restrictions flagged for this society in {loc}.")

                # Metro proximity
                dist_match = re.search(r"distance_km=([\d.]+)[^)]*metro", last_msg, re.IGNORECASE)
                if dist_match:
                    dist_val = float(dist_match.group(1))
                    if dist_val > 2.5:
                        red_flags.append(f"Metro station is {dist_val}km away, exceeding the preferred walking distance buffer.")
                else:
                    red_flags.append("Metro station is >3km away, exceeding the comfortable walking buffer for daily commutes.")

                return json.dumps({
                    "fair_range_min": fair_range_min,
                    "fair_range_max": fair_range_max,
                    "overpriced_percentage": overpriced,
                    "red_flags": red_flags,
                    "neighbourhood_score": 5.0,
                    "broker_questionnaire": [
                        f"Is the water supply Cauvery water, or does this society in {loc} rely entirely on tankers?",
                        "Is the vegetarian-only restriction strictly enforced, or is it a request from the landlord?",
                        "Does the rent include maintenance charges or are they collected separately?",
                        "Are there any dedicated parking spaces allocated for 2-wheelers or 4-wheelers?"
                    ]
                })

            # 2. Financials extraction (Must be checked first or explicitly)
            elif "financial extractor" in last_msg.lower() or "price_per_sqft" in last_msg.lower():
                rent = 35000.0
                rent_match = re.search(r"(?:rent|rent is|pricing is|inr|rs\.?)\s*(\d+(?:,\d+)*)", last_msg, re.IGNORECASE)
                if rent_match:
                    rent = float(rent_match.group(1).replace(",", ""))
                    
                deposit = rent * 5.0
                deposit_match = re.search(r"(?:deposit|security deposit|dep)\s*(?:is)?\s*(\d+(?:,\d+)*)", last_msg, re.IGNORECASE)
                if deposit_match:
                    deposit = float(deposit_match.group(1).replace(",", ""))
                else:
                    lakh_match = re.search(r"(\d+)\s*(?:lakh|lakhs|lac|lacs)\s*deposit", last_msg, re.IGNORECASE)
                    if lakh_match:
                        deposit = float(lakh_match.group(1)) * 100000.0
                        
                sqft = 1200.0
                sqft_match = re.search(r"(\d+(?:,\d+)*)\s*(?:sqft|sq ft|sq\.?ft|square feet|areaSqFt)", last_msg, re.IGNORECASE)
                if sqft_match:
                    sqft = float(sqft_match.group(1).replace(",", ""))
                    
                return json.dumps({
                    "rent": rent,
                    "deposit": deposit,
                    "area_sqft": sqft,
                    "price_per_sqft": round(rent / sqft, 1) if sqft else None
                })

            # 2. Vibe extraction
            elif "vibe check agent" in last_msg.lower() or "community_signals" in last_msg.lower():
                diffs = []
                signals = ["Quiet residential community"]
                rules = []
                
                if "metro" in last_msg.lower() and "drive" in last_msg.lower():
                    diffs.append("Listing claims metro is nearby, but notes a drive is required.")
                if "veg" in last_msg.lower():
                    rules.append("Pure veg preferred")
                if "no pets" in last_msg.lower() or "pets" in last_msg.lower():
                    rules.append("No pets allowed")
                    
                return json.dumps({
                    "amenity_vs_claim_diffs": diffs,
                    "community_signals": signals,
                    "diet_pet_lifestyle": rules,
                    "listing_nlp_sentiment": "Pressuring" if "urgent" in last_msg.lower() else "Neutral"
                })

            # 3. Address resolution
            elif "address" in last_msg.lower() or "locality" in last_msg.lower():
                target_text = last_msg.lower()
                if "raw listing content:" in target_text:
                    target_text = target_text.split("raw listing content:", 1)[1]
                
                loc = "Whitefield"
                structured = "Whitefield Main Rd, Bangalore, KA"
                lat, lon = 12.9698, 77.7500
                
                if "koramangala" in target_text:
                    loc = "Koramangala"
                    structured = "Koramangala 4th Block, Bangalore, KA"
                    lat, lon = 12.9352, 77.6244
                elif "indiranagar" in target_text:
                    loc = "Indiranagar"
                    structured = "Indiranagar 100 Feet Rd, Bangalore, KA"
                    lat, lon = 12.9784, 77.6408
                elif "domlur" in target_text:
                    loc = "Domlur"
                    structured = "Domlur 2nd Stage, Bangalore, KA"
                    lat, lon = 12.9610, 77.6387
                elif "hsr" in target_text:
                    loc = "HSR Layout"
                    structured = "HSR Layout Sector 2, Bangalore, KA"
                    lat, lon = 12.9141, 77.6411
                    
                return json.dumps({
                    "locality": loc,
                    "city": "Bangalore",
                    "structured_address": structured,
                    "lat": lat,
                    "lon": lon
                })
            
            return "Mock response: " + last_msg[:100]

        @property
        def _llm_type(self) -> str:
            return "mock-chat-model"

    if use_mock:
        log.warning("Returning MockChatModel wrapped in ResilientChatModel for local execution.")
        mock_instance = MockChatModel()
        return ResilientChatModel(real_model=mock_instance, mock_model=mock_instance, use_mock=True)

    try:
        if provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            model_name = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
            log.info(f"Initializing ChatGoogleGenerativeAI with model: {model_name}")
            model = ChatGoogleGenerativeAI(
                model=model_name,
                temperature=temperature,
                google_api_key=os.environ.get("GEMINI_API_KEY"),
            )
        else:
            log.info("Initializing ChatBedrock with model: anthropic.claude-3-sonnet-20240229-v1:0")
            model = ChatBedrock(
                model_id="anthropic.claude-3-sonnet-20240229-v1:0",
                region_name=aws_region,
                model_kwargs={"temperature": temperature},
            )
        # Return resilient model wrapper to automatically handle client/network errors
        return ResilientChatModel(real_model=model, mock_model=MockChatModel(), use_mock=False)
    except Exception as e:
        log.error(f"Failed to initialize {provider.capitalize()} Chat model: {e}. Falling back to MockChatModel wrapper.")
        mock_instance = MockChatModel()
        return ResilientChatModel(real_model=mock_instance, mock_model=mock_instance, use_mock=True)


# ── Elasticsearch Initialization ───────────────────────────────────────────────
def get_elasticsearch_client() -> Elasticsearch:
    """Returns initialized client for Elasticsearch."""
    client_opts = {
        "hosts": [{
            "host": global_config.ES_HOST,
            "port": global_config.ES_PORT,
            "scheme": global_config.ES_SCHEME,
        }],
        "request_timeout": 15,
    }
    if global_config.ES_API_KEY:
        client_opts["api_key"] = global_config.ES_API_KEY
    else:
        client_opts["basic_auth"] = global_config.es_auth
    return Elasticsearch(**client_opts)


# ── Jina Reranker / Rerank Mock ────────────────────────────────────────────────
def rerank_listings(query: str, listings: list[dict], top_k: int = 3) -> list[dict]:
    """
    Uses Jina Rerank to find the closest fitting properties.
    Falls back to scoring by string metrics if Jina credentials are not set.
    """
    jina_api_key = os.environ.get("JINA_API_KEY")
    if not jina_api_key or not listings:
        log.info("Jina API key not found or listings empty. Using fallback BM25-alike string scoring for reranking.")
        # Fallback simple search query matching
        scored = []
        query_terms = set(query.lower().split())
        for lst in listings:
            title = lst.get("title", "").lower()
            desc = lst.get("description", "").lower()
            score = 0.0
            for term in query_terms:
                if term in title:
                    score += 2.0
                if term in desc:
                    score += 1.0
            scored.append((score, lst))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [lst for _, lst in scored[:top_k]]

    try:
        from jina_reranker_client import RerankerClient
        client = RerankerClient(api_key=jina_api_key)
        # Format documents for Jina reranker
        documents = [
            {"id": idx, "text": f"{lst.get('title', '')} - {lst.get('description', '')} at {lst.get('address', '')}"}
            for idx, lst in enumerate(listings)
        ]
        results = client.rerank(query=query, documents=documents, top_n=top_k)
        
        selected = []
        for result in results:
            target_idx = int(result["document"]["id"])
            selected.append(listings[target_idx])
        return selected
    except Exception as e:
        log.warning(f"Error running Jina Rerank: {e}. Falling back to BM25 sequence matching.")
        return listings[:top_k]
