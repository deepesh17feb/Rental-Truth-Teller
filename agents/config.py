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


# ── LLM Client Initialization (Gemini + Bedrock + Fallback Mock) ────────────────
def get_llm(temperature: float = 0.1) -> BaseChatModel:
    """Returns the configured LLM Chat Model (Gemini or AWS Bedrock Claude)."""
    provider = global_config.LLM_PROVIDER.lower().strip()
    
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        if not global_config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is missing")
        log.info(f"Initializing ChatGoogleGenerativeAI with model: {global_config.GEMINI_MODEL}")
        return ChatGoogleGenerativeAI(
            model=global_config.GEMINI_MODEL,
            temperature=temperature,
            google_api_key=global_config.GEMINI_API_KEY,
        )
    elif provider == "bedrock":
        log.info("Initializing ChatBedrock with model: anthropic.claude-3-sonnet-20240229-v1:0")
        return ChatBedrock(
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            region_name=global_config.AWS_DEFAULT_REGION,
            model_kwargs={"temperature": temperature},
        )
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


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
