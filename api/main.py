"""
api/main.py
───────────
FastAPI Entrypoint for the Rental Truth-Teller Multi-Agent System.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from agents.service import TruthTellerService
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
