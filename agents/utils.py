import json

def parse_json_from_llm(content: str) -> dict:
    """Safely extracts and parses JSON from the LLM's response string."""
    if content.startswith("```json"):
        content = content.replace("```json", "", 1)
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    content = content.strip()
    return json.loads(content)
