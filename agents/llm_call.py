"""
agents/llm_call.py
────────────────────
Shared helper for calling an LLM with a prompt template, parsing the
response into a pydantic schema via PydanticOutputParser, and retrying
with exponential backoff on any failure (network error or parse failure).
Replaces the old hand-rolled agents/utils.py::parse_json_from_llm pattern.
"""

from __future__ import annotations

import logging
from typing import Type, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from tenacity import Retrying, stop_after_attempt, wait_exponential

from agents.config import get_response_text

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMCallError(Exception):
    """Raised when a structured LLM call fails after all retry attempts."""


def call_llm_structured(
    llm: BaseChatModel,
    prompt_template: str,
    input_vars: dict,
    output_schema: Type[T],
    max_attempts: int = 3,
    wait_min: float = 1.0,
    wait_max: float = 8.0,
) -> T:
    """Invokes `llm` with `prompt_template` filled by `input_vars`, parses the
    response into `output_schema`, retrying up to `max_attempts` times with
    exponential backoff on any failure. Raises LLMCallError if every
    attempt fails."""
    parser = PydanticOutputParser(pydantic_object=output_schema)
    prompt = ChatPromptTemplate.from_template(
        prompt_template + "\n\n{format_instructions}"
    ).partial(format_instructions=parser.get_format_instructions())
    chain = prompt | llm

    def _call() -> T:
        response = chain.invoke(input_vars)
        text = get_response_text(response)
        return parser.parse(text)

    retryer = Retrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=wait_min, min=wait_min, max=wait_max),
        reraise=True,
    )
    try:
        return retryer(_call)
    except Exception as e:
        log.error(f"[call_llm_structured] Failed after {max_attempts} attempts: {e}")
        raise LLMCallError(str(e)) from e
