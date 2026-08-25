import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from agents.llm_call import call_llm_structured, LLMCallError
from agents.schemas import BenchmarksResult


def test_call_llm_structured_success():
    fake_llm = RunnableLambda(
        lambda _: AIMessage(content='{"avg_price_per_sqft": 42.0, "std_price_per_sqft": 6.0}')
    )

    result = call_llm_structured(
        fake_llm, "Locality: {locality}", {"locality": "Whitefield"}, BenchmarksResult
    )

    assert result.avg_price_per_sqft == 42.0
    assert result.std_price_per_sqft == 6.0


def test_call_llm_structured_retries_then_succeeds():
    calls = {"n": 0}

    def fake_invoke(_prompt_value):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient network error")
        return AIMessage(content='{"avg_price_per_sqft": 42.0, "std_price_per_sqft": 6.0}')

    fake_llm = RunnableLambda(fake_invoke)

    result = call_llm_structured(
        fake_llm,
        "Locality: {locality}",
        {"locality": "X"},
        BenchmarksResult,
        wait_min=0.01,
        wait_max=0.05,
    )

    assert calls["n"] == 3
    assert result.avg_price_per_sqft == 42.0


def test_call_llm_structured_raises_after_max_attempts():
    fake_llm = RunnableLambda(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(LLMCallError):
        call_llm_structured(
            fake_llm,
            "Locality: {locality}",
            {"locality": "X"},
            BenchmarksResult,
            max_attempts=2,
            wait_min=0.01,
            wait_max=0.05,
        )


def test_call_llm_structured_malformed_json_raises_after_retries():
    fake_llm = RunnableLambda(lambda _: AIMessage(content="not json at all"))

    with pytest.raises(LLMCallError):
        call_llm_structured(
            fake_llm,
            "Locality: {locality}",
            {"locality": "X"},
            BenchmarksResult,
            max_attempts=2,
            wait_min=0.01,
            wait_max=0.05,
        )
