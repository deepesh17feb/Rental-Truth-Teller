import re
from typing import Optional

def parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    text = str(text).replace(",", "").replace("₹", "").replace("Rs", "").strip()
    m = re.search(r"([\d.]+)\s*(cr|lac|lakh|k)?", text, re.IGNORECASE)
    if not m:
        return None
    value = float(m.group(1))
    suffix = (m.group(2) or "").lower()
    return value * {"cr": 1e7, "lac": 1e5, "lakh": 1e5, "k": 1e3}.get(suffix, 1)

def parse_area_sqft(text: str) -> Optional[float]:
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*sq", str(text), re.IGNORECASE)
    return float(m.group(1).replace(",", "")) if m else None

def extract_bhk(text: str) -> Optional[int]:
    m = re.search(r"(\d+)\s*(?:BHK|bhk|bedroom|Bedroom)", str(text))
    return int(m.group(1)) if m else None

def clean_text(text) -> str:
    return " ".join(str(text).split()).strip() if text else ""
