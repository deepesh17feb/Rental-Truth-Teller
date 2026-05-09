"""
crawler/items.py
────────────────
Scrapy Item definitions for Bangalore property data.
These are the canonical data contracts between spiders and pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class GeoPoint:
    lat: float
    lon: float


@dataclass
class PropertyItem:
    """
    Canonical property record produced by every spider.
    Maps 1-to-1 with the Elasticsearch document schema.
    """

    # ── Identity ─────────────────────────────────────────────────────────────
    source: str                         # "magicbricks" | "99acres"
    source_id: str                      # ID as used on the source site
    url: str                            # Canonical listing URL
    crawled_at: datetime = field(default_factory=datetime.utcnow)

    # ── Location ──────────────────────────────────────────────────────────────
    area: str = ""                      # Locality name  e.g. "Whitefield"
    city: str = "Bangalore"
    state: str = "Karnataka"
    pincode: str = ""
    address: str = ""
    geo: Optional[GeoPoint] = None      # lat/lon for geo-search in ES

    # ── Listing Meta ─────────────────────────────────────────────────────────
    title: str = ""
    description: str = ""
    transaction_type: str = ""          # "rent" | "sale"
    property_type: str = ""             # "apartment" | "villa" | "plot" | ...
    posted_by: str = ""                 # "owner" | "agent" | "builder"
    posted_date: Optional[str] = None   # ISO date string

    # ── Specs ─────────────────────────────────────────────────────────────────
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    area_sqft: Optional[float] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    furnishing: str = ""                # "furnished" | "semi-furnished" | "unfurnished"
    facing: str = ""                    # e.g. "East" | "North"
    age_of_property: str = ""

    # ── Financials ────────────────────────────────────────────────────────────
    price: Optional[float] = None       # In INR
    price_unit: str = "INR"
    price_per_sqft: Optional[float] = None
    deposit: Optional[float] = None     # For rentals
    maintenance: Optional[float] = None

    # ── Amenities ─────────────────────────────────────────────────────────────
    amenities: List[str] = field(default_factory=list)

    # ── Media ─────────────────────────────────────────────────────────────────
    images: List[str] = field(default_factory=list)

    def to_es_doc(self) -> dict:
        """
        Serialize to an Elasticsearch document ready for ELSER indexing.

        Dual-field strategy:
          • Regular fields  → BM25 / keyword filtering (unchanged)
          • *_semantic fields → semantic_text type; ES calls ELSER at index time.

        The four semantic_text fields are populated with plain text derived from
        the corresponding source fields.  Elasticsearch handles all inference
        server-side — no Python embedding step is needed.
        """
        doc = {
            # ── Identity ──────────────────────────────────────────────────────
            "source":           self.source,
            "source_id":        self.source_id,
            "url":              self.url,
            "crawled_at":       self.crawled_at.isoformat(),

            # ── Location ──────────────────────────────────────────────────────
            "area":             self.area,
            "city":             self.city,
            "state":            self.state,
            "pincode":          self.pincode,
            "address":          self.address,

            # ── Listing Meta ──────────────────────────────────────────────────
            "title":            self.title,
            "description":      self.description,
            "transaction_type": self.transaction_type,
            "property_type":    self.property_type,
            "posted_by":        self.posted_by,
            "posted_date":      self.posted_date,

            # ── Specs ─────────────────────────────────────────────────────────
            "bedrooms":         self.bedrooms,
            "bathrooms":        self.bathrooms,
            "area_sqft":        self.area_sqft,
            "floor":            self.floor,
            "total_floors":     self.total_floors,
            "furnishing":       self.furnishing,
            "facing":           self.facing,
            "age_of_property":  self.age_of_property,

            # ── Financials ────────────────────────────────────────────────────
            "price":            self.price,
            "price_unit":       self.price_unit,
            "price_per_sqft":   self.price_per_sqft,
            "deposit":          self.deposit,
            "maintenance":      self.maintenance,

            # ── Amenities (keyword list for exact filtering) ──────────────────
            "amenities":        self.amenities,

            # ── Media ─────────────────────────────────────────────────────────
            "images":           self.images,
        }

        # ── Geo ───────────────────────────────────────────────────────────────
        if self.geo:
            doc["geo"] = {"lat": self.geo.lat, "lon": self.geo.lon}

        # ── ELSER semantic_text fields ────────────────────────────────────────
        # These fields are typed `semantic_text` in the index mapping.
        # ES invokes the ELSER inference endpoint automatically at index time.
        # We only send plain-text strings; no client-side embedding needed.
        if self.title:
            doc["title_semantic"] = self.title

        if self.description:
            doc["description_semantic"] = self.description

        if self.amenities:
            # Join the list into a single sentence so ELSER can encode it holistically.
            # e.g. "swimming pool gym covered parking 24/7 security clubhouse"
            doc["amenities_semantic"] = " ".join(self.amenities)

        if self.address:
            doc["address_semantic"] = self.address

        # Strip None / empty-string values so ES doesn't reject the document
        return {k: v for k, v in doc.items() if v is not None and v != ""}
