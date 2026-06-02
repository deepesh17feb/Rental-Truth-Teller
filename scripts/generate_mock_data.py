"""
scripts/generate_mock_data.py
──────────────────────────────
Generates realistic Bangalore property records and pushes them through
the full Tier-0 pipeline (JSONL file + Elasticsearch / ELSER indexing).

Use this to:
  1. Prove the complete pipeline works end-to-end without needing real crawl access.
  2. Pre-populate the ES index for search / Kibana demo purposes.
  3. Validate ELSER semantic indexing before live crawl data arrives.

Usage:
    python3 scripts/generate_mock_data.py                  # 100 records, write JSONL + ES
    python3 scripts/generate_mock_data.py --count 500      # more records
    python3 scripts/generate_mock_data.py --no-es          # JSONL only
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

from config.settings import config
from config.areas import TARGET_AREAS
# ─────────────────────────────────────────────────────────────────────────────
# Data pools for realistic generation
# ─────────────────────────────────────────────────────────────────────────────

PROPERTY_TITLES = {
    "Whitefield": [
        "Spacious {bhk} BHK Apartment near ITPL",
        "{bhk} BHK Flat in Prestige Shantiniketan, Whitefield",
        "Modern {bhk} BHK in Brigade Metropolis",
        "Cozy {bhk} BHK near Whitefield Bus Stand",
        "{bhk} BHK in Salarpuria Sattva, Whitefield",
        "Premium {bhk} BHK with Clubhouse in Varthur Road",
        "{bhk} BHK Studio Apartment near Hoodi Junction",
        "Fully Furnished {bhk} BHK near EPIP Zone",
        "{bhk} BHK in Embassy Springs, Whitefield",
        "Gated Community {bhk} BHK in Marathahalli",
    ],
    "Koramangala": [
        "{bhk} BHK Apartment in Koramangala 5th Block",
        "Luxury {bhk} BHK near Forum Mall, Koramangala",
        "{bhk} BHK Flat in 4th Block Koramangala",
        "Modern {bhk} BHK near Sony World Signal",
        "Spacious {bhk} BHK in 6th Block Koramangala",
        "{bhk} BHK with Terrace in 1st Block Koramangala",
        "Semi-Furnished {bhk} BHK near Jyoti Nivas College",
        "{bhk} BHK in Koramangala 8th Block",
        "Premium {bhk} BHK with Lake View, Koramangala",
        "Independent {bhk} BHK House in 2nd Block",
    ],
}

DESCRIPTIONS = [
    (
        "Beautiful {bhk} BHK apartment in the heart of {area}, Bangalore. "
        "Offers excellent connectivity to IT parks and major roads. "
        "The property features {amenity1}, {amenity2}, and {amenity3}. "
        "Ideal for working professionals and families. "
        "Well-maintained society with 24/7 security and power backup."
    ),
    (
        "Spacious and well-ventilated {bhk} BHK flat available in {area}. "
        "Located close to metro station and shopping centres. "
        "Comes with {amenity1} and {amenity2}. "
        "Society amenities include {amenity3} and children's play area. "
        "Excellent investment opportunity with good rental yield."
    ),
    (
        "Ready-to-move {bhk} BHK apartment in a premium gated community in {area}. "
        "The flat is {furnishing} and features modular kitchen. "
        "Complex has {amenity1}, {amenity2}, and jogging track. "
        "Located minutes from prominent tech parks and hospitals. "
        "Vastu-compliant with East-facing orientation."
    ),
    (
        "Luxurious {bhk} BHK unit in one of {area}'s most sought-after societies. "
        "High-end fittings, vitrified flooring, and large balconies. "
        "Building amenities: {amenity1}, {amenity2}, {amenity3}, indoor games room. "
        "Well-connected to Outer Ring Road and main arterial roads. "
        "Freshly painted and ready for immediate occupancy."
    ),
]

AMENITIES_POOL = [
    "Swimming Pool", "Gym", "Covered Parking", "Club House", "24/7 Security",
    "Power Backup", "Children's Play Area", "Jogging Track", "Badminton Court",
    "Indoor Games Room", "Visitor Parking", "Garden Area", "CCTV Surveillance",
    "Lift", "Intercom", "Rainwater Harvesting", "Solar Energy", "Gas Pipeline",
    "Vastu Compliant", "Gated Community", "Tennis Court", "Squash Court",
    "Yoga Room", "Party Hall", "Amphitheatre",
]

SOCIETIES = {
    "Whitefield": [
        "Prestige Shantiniketan", "Brigade Metropolis", "Salarpuria Sattva East Crest",
        "Embassy Springs", "Sobha Dream Acres", "Godrej United", "Purva Whitehall",
        "Mantri Lithos", "Adarsh Palm Retreat", "Phoenix One Bangalore West",
    ],
    "Koramangala": [
        "Sobha Carnation", "Brigade Corniche", "Prestige Ivy League", "Adarsh Residency",
        "Raheja Residency", "Nitesh Long Island", "SNN Raj Etternia",
        "Alliance Orchid Springs", "Green Woods", "Ittina Properties",
    ],
}

FACING = ["East", "West", "North", "South", "North-East", "South-East"]
FURNISHING = ["furnished", "semi-furnished", "unfurnished"]
PROPERTY_TYPES = ["apartment", "villa", "independent_house"]
POSTED_BY = ["owner", "agent", "builder"]
SOURCES = ["magicbricks", "99acres"]

PRICE_RANGES = {
    # (min_rent, max_rent, min_sale, max_sale) — in INR
    "Whitefield": {
        1: (12_000,  30_000,   3_500_000,  6_000_000),
        2: (18_000,  45_000,   5_500_000,  9_000_000),
        3: (28_000,  80_000,   8_000_000, 15_000_000),
        4: (50_000, 150_000,  14_000_000, 30_000_000),
    },
    "Koramangala": {
        1: (16_000,  35_000,   4_500_000,  8_000_000),
        2: (25_000,  60_000,   7_000_000, 12_000_000),
        3: (40_000, 100_000,  12_000_000, 22_000_000),
        4: (70_000, 200_000,  20_000_000, 45_000_000),
    },
}

# Slight geo scatter within each area
GEO_SCATTER = {
    "Whitefield":  {"lat": 12.9698, "lon": 77.7500, "spread": 0.02},
    "Koramangala": {"lat": 12.9352, "lon": 77.6245, "spread": 0.015},
}


def _random_date_recent(days_back: int = 90) -> str:
    d = datetime.utcnow() - timedelta(days=random.randint(0, days_back))
    return d.strftime("%Y-%m-%d")


def _scatter_geo(area_name: str) -> GeoPoint:
    g = GEO_SCATTER[area_name]
    return GeoPoint(
        lat=g["lat"] + random.uniform(-g["spread"], g["spread"]),
        lon=g["lon"] + random.uniform(-g["spread"], g["spread"]),
    )


def generate_property(area_name: str, source: str, idx: int) -> PropertyItem:
    """Generate one realistic PropertyItem for the given area."""
    bhk        = random.choices([1, 2, 3, 4], weights=[15, 40, 35, 10])[0]
    tx_type    = random.choice(["rent", "sale"])
    furnishing = random.choice(FURNISHING)
    prop_type  = random.choices(
        PROPERTY_TYPES, weights=[75, 15, 10]
    )[0]

    # Price
    price_range = PRICE_RANGES[area_name][bhk]
    if tx_type == "rent":
        price   = random.randint(price_range[0], price_range[1])
        deposit = price * random.randint(2, 6)
    else:
        price   = random.randint(price_range[2], price_range[3])
        deposit = None

    area_sqft     = bhk * random.randint(450, 600) + random.randint(0, 200)
    price_per_sqft = round(price / area_sqft, 2) if tx_type == "sale" else None

    # Amenities — 4–10 random amenities
    amenities = random.sample(AMENITIES_POOL, k=random.randint(4, 10))

    # Title
    title_tmpl = random.choice(PROPERTY_TITLES[area_name])
    title      = title_tmpl.format(bhk=bhk)

    # Description
    desc_tmpl  = random.choice(DESCRIPTIONS)
    description = desc_tmpl.format(
        bhk       = bhk,
        area      = area_name,
        furnishing= furnishing,
        amenity1  = amenities[0],
        amenity2  = amenities[1] if len(amenities) > 1 else "parking",
        amenity3  = amenities[2] if len(amenities) > 2 else "gym",
    )

    # Society / address
    society = random.choice(SOCIETIES[area_name])
    block   = random.randint(1, 10)
    address = f"{society}, Block {block}, {area_name}, Bangalore"

    # Source ID
    source_id = f"mock-{source}-{area_name[:3].lower()}-{idx:06d}"

    return PropertyItem(
        source           = source,
        source_id        = source_id,
        url              = f"https://www.{source.replace('99acres','99acres.com')}.com/property/{source_id}",
        area             = area_name,
        city             = "Bangalore",
        state            = "Karnataka",
        address          = address,
        title            = title,
        description      = description,
        transaction_type = tx_type,
        property_type    = prop_type,
        posted_by        = random.choice(POSTED_BY),
        posted_date      = _random_date_recent(),
        bedrooms         = bhk,
        bathrooms        = max(1, bhk - 1),
        area_sqft        = float(area_sqft),
        floor            = random.randint(0, 20),
        total_floors     = random.randint(5, 25),
        furnishing       = furnishing,
        facing           = random.choice(FACING),
        price            = float(price),
        price_per_sqft   = price_per_sqft,
        deposit          = float(deposit) if deposit else None,
        amenities        = amenities,
        geo              = _scatter_geo(area_name),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def run(count: int, no_es: bool) -> None:
    ts       = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"mock_properties_{ts}.jsonl"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ES client
    es_client = None
    es_ok     = False
    if not no_es and config.ES_API_KEY:
        try:
            from config.es_client import build_es_client
            from elasticsearch import helpers, exceptions as es_exc
            es_client = build_es_client(request_timeout=120)
            es_client.info()
            es_ok = True
            log.info("ES connected → %s", config.es_url)
            # Ensure index exists
            if not es_client.indices.exists(index=config.ES_INDEX_PROPERTIES):
                log.warning("Index '%s' missing — run setup_es_index.py first.", config.ES_INDEX_PROPERTIES)
                es_ok = False
        except Exception as exc:
            log.warning("ES unavailable (%s) — writing JSONL only.", exc)

    log.info("=" * 60)
    log.info("Generating %d mock Bangalore property records", count)
    log.info("  Areas  : Whitefield, Koramangala")
    log.info("  Sources: magicbricks, 99acres")
    log.info("  Output : %s", out_path)
    log.info("  ES push: %s", "YES" if es_ok else "NO")
    log.info("=" * 60)

    areas   = list(TARGET_AREAS.values())
    sources = SOURCES
    buffer  = []
    indexed = 0
    errors  = 0

    with open(out_path, "w", encoding="utf-8") as fh:
        for i in range(count):
            area   = areas[i % len(areas)]
            source = sources[i % len(sources)]

            item = generate_property(area.name, source, i)
            doc  = item.to_es_doc()

            # Write JSONL immediately
            fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
            fh.flush()

            if (i + 1) % 20 == 0:
                log.info(
                    "  [%d/%d] %s | %s | %s | ₹%s | %s BHK | %s",
                    i + 1, count,
                    item.source, item.area, item.transaction_type,
                    f"{int(item.price):,}", item.bedrooms, item.furnishing,
                )

            # ES bulk buffer
            if es_ok:
                import hashlib
                doc_id = hashlib.sha256(
                    f"{item.source}::{item.source_id}".encode()
                ).hexdigest()
                buffer.append({
                    "_op_type": "index",
                    "_index":   config.ES_INDEX_PROPERTIES,
                    "_id":      doc_id,
                    **doc,
                })

                # Flush every 10 (ELSER inference latency)
                if len(buffer) >= 10:
                    ok, errs = _flush_to_es(es_client, buffer)
                    indexed += ok
                    errors  += len(errs) if errs else 0
                    buffer.clear()

        # Final ES flush
        if es_ok and buffer:
            ok, errs = _flush_to_es(es_client, buffer)
            indexed += ok
            errors  += len(errs) if errs else 0

    log.info("=" * 60)
    log.info("Done!")
    log.info("  JSONL records : %d → %s", count, out_path)
    if es_ok:
        log.info("  ES indexed    : %d  errors: %d", indexed, errors)
    log.info("=" * 60)


def _flush_to_es(client, buffer: list) -> tuple:
    try:
        from elasticsearch import helpers
        ok, errors = helpers.bulk(
            client, buffer,
            raise_on_error=False,
            raise_on_exception=False,
        )
        log.info("  ES flush → +%d indexed", ok)
        return ok, errors
    except Exception as exc:
        log.error("  ES flush error: %s", exc)
        return 0, [str(exc)]


def main() -> None:
    p = argparse.ArgumentParser(description="Generate mock Bangalore property data")
    p.add_argument("--count",  type=int, default=100, help="Number of records to generate")
    p.add_argument("--no-es",  action="store_true",   help="Skip Elasticsearch — JSONL only")
    args = p.parse_args()
    run(args.count, args.no_es)


if __name__ == "__main__":
    main()
