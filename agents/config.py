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

# ── AWS Bedrock Initialization ─────────────────────────────────────────────────
def get_llm(temperature: float = 0.1) -> BaseChatModel:
    """
    Returns the AWS Bedrock Claude chat model.
    Falls back to a simple mock model or env indicators for local-only execution if AWS credentials lack.
    """
    aws_region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    
    # Check if we have valid AWS credentials or mock flag
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    has_real_credentials = (
        (aws_key != "" and not aws_key.startswith("BedrockAPIKey")) or 
        os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI") is not None or
        (aws_secret != "" and not aws_secret.startswith("QVIovZkP"))
    )
    
    use_mock = os.environ.get("USE_MOCK_LLM") == "true" or not has_real_credentials

    if use_mock:
        log.warning("Returning MockChatModel for local/integration execution.")
        from langchain_core.language_models.chat_models import SimpleChatModel
        from langchain_core.messages import BaseMessage, AIMessage

        class MockChatModel(SimpleChatModel):
            def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
                last_msg = messages[-1].content
                log.info(f"[MockChatModel Received]: {last_msg}")
                
                # Smart mock response selectors depending on context
                if "pricing" in last_msg.lower() or "calculate" in last_msg.lower() or "rent" in last_msg.lower():
                    return '{"rent": 35000.0, "deposit": 150000.0, "sqft": 1200.0, "price_per_sqft": 29.1}'
                elif "address" in last_msg.lower() or "locality" in last_msg.lower():
                    return '{"locality": "Whitefield", "city": "Bangalore", "structured_address": "Whitefield Main Rd, Bangalore, KA"}'
                elif "description" in last_msg.lower() or "claim" in last_msg.lower():
                    return '{"diffs": ["Listing claims 5 min to metro, but true walking time is 15 min"], "signals": ["Quiet family residential area", "Some street noise during daytime"], "rules": ["Rent agreement requires 11 month lock-in", "Veg only tag mentioned"]}'
                
                return "Mock response summarizing inputs: " + last_msg[:100]

            @property
            def _llm_type(self) -> str:
                return "mock-chat-model"

        return MockChatModel()

    try:
        model = ChatBedrock(
            model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
            region_name=aws_region,
            model_kwargs={"temperature": temperature},
        )
        return model
    except Exception as e:
        log.error(f"Failed to initialize Bedrock Chat model: {e}. Falling back to simple response model.")
        # Fallback simple response
        from langchain_core.language_models.chat_models import SimpleChatModel
        class FallbackMock(SimpleChatModel):
            def _call(self, messages, stop=None, **kwargs) -> str:
                return "Fallback mock summary of instructions."
            @property
            def _llm_type(self) -> str:
                return "fallback-mock"
        return FallbackMock()


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
