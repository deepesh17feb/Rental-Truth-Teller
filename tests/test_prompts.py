from agents import prompts

ALL_PROMPTS = [
    prompts.GEOCODE_PROMPT,
    prompts.EXTRACT_FINANCIALS_PROMPT,
    prompts.ESTIMATE_BENCHMARKS_PROMPT,
    prompts.VIBE_CHECK_PROMPT,
    prompts.RESOLVE_NEIGHBOURHOOD_PROMPT,
    prompts.SYNTHESIS_PROMPT,
]


def test_prompts_no_longer_hand_roll_json_instructions():
    for prompt in ALL_PROMPTS:
        assert "raw JSON" not in prompt
        assert "```" not in prompt


def test_prompts_still_have_their_input_variables():
    assert "{listing_input}" in prompts.GEOCODE_PROMPT
    assert "{listing_input}" in prompts.EXTRACT_FINANCIALS_PROMPT
    assert "{locality}" in prompts.ESTIMATE_BENCHMARKS_PROMPT
    assert "{listing_input}" in prompts.VIBE_CHECK_PROMPT
    assert "{locality}" in prompts.RESOLVE_NEIGHBOURHOOD_PROMPT
    assert "{structured_address}" in prompts.RESOLVE_NEIGHBOURHOOD_PROMPT
    assert "{address_resolved}" in prompts.SYNTHESIS_PROMPT
    assert "{pricing_data}" in prompts.SYNTHESIS_PROMPT
    assert "{vibe_data}" in prompts.SYNTHESIS_PROMPT
    assert "{neighbourhood_data}" in prompts.SYNTHESIS_PROMPT
    assert "{critique_section}" in prompts.SYNTHESIS_PROMPT
