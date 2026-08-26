"""
api/main.py
───────────
FastAPI Entrypoint for the Rental Truth-Teller Multi-Agent System.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List

from agents.service import TruthTellerService
from agents.persistence import list_verdicts, get_verdict, VerdictSummary, VerdictDetail
from config.logging_utils import setup_logging
from config.settings import config

# Setup backend logging
setup_logging(log_file=config.BACKEND_LOG_PATH)

app = FastAPI(
    title="Rental Truth-Teller API",
    description="Multi-agent verification network for Bangalore real estate listings.",
    version="1.0.0"
)

class ListingRequest(BaseModel):
    text: str

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/verify")
def verify_listing(request: ListingRequest):
    """
    Analyzes a rental listing and returns a verified verdict card.
    Note: We use 'def' instead of 'async def' because the underlying service
    layer is synchronous and performs blocking I/O (LLM calls).
    """
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Listing text cannot be empty.")

    try:
        result = TruthTellerService.verify_listing(request.text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")

@app.get("/verdicts", response_model=List[VerdictSummary])
def list_verdicts_endpoint(limit: int = 20):
    """Returns the most recent persisted verdicts, newest first."""
    return list_verdicts(limit=limit)

@app.get("/verdicts/{verdict_id}", response_model=VerdictDetail)
def get_verdict_endpoint(verdict_id: str):
    """Returns the full persisted record for one verdict id."""
    detail = get_verdict(verdict_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Verdict not found.")
    return detail

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
