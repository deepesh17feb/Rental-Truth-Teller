"""
tests/test_items.py
────────────────────
Unit tests for PropertyItem serialization and price parsing utilities.
"""

from crawler.items import PropertyItem, GeoPoint
from crawler.spiders.base_spider import BangalorePropertySpider


class TestParsePricing:
    def test_crore(self):
        assert BangalorePropertySpider.parse_price("₹ 1.5 Cr") == 15_000_000

    def test_lac(self):
        assert BangalorePropertySpider.parse_price("₹ 45 Lac") == 4_500_000

    def test_plain(self):
        assert BangalorePropertySpider.parse_price("₹ 25,000") == 25_000

    def test_empty(self):
        assert BangalorePropertySpider.parse_price("") is None

    def test_none(self):
        assert BangalorePropertySpider.parse_price(None) is None


class TestParseAreaSqft:
    def test_sqft(self):
        assert BangalorePropertySpider.parse_area_sqft("1200 sq.ft") == 1200.0

    def test_commas(self):
        assert BangalorePropertySpider.parse_area_sqft("1,200 Sq.Ft") == 1200.0

    def test_empty(self):
        assert BangalorePropertySpider.parse_area_sqft("") is None


class TestPropertyItemSerialization:
    def test_to_es_doc_basic(self):
        item = PropertyItem(
            source="magicbricks",
            source_id="12345678",
            url="https://example.com/property/12345678",
            area="Whitefield",
            city="Bangalore",
            price=5_000_000,
            bedrooms=3,
        )
        doc = item.to_es_doc()
        assert doc["source"] == "magicbricks"
        assert doc["area"] == "Whitefield"
        assert doc["price"] == 5_000_000
        assert doc["bedrooms"] == 3
        # None values should be excluded
        assert "deposit" not in doc

    def test_to_es_doc_with_geo(self):
        item = PropertyItem(
            source="99acres",
            source_id="99999999",
            url="https://example.com/p/99999999",
            area="Koramangala",
            city="Bangalore",
            geo=GeoPoint(lat=12.9352, lon=77.6245),
        )
        doc = item.to_es_doc()
        assert doc["geo"] == {"lat": 12.9352, "lon": 77.6245}

    def test_to_es_doc_excludes_empty_strings(self):
        item = PropertyItem(
            source="magicbricks",
            source_id="11111111",
            url="https://example.com",
            furnishing="",  # empty string should be excluded
        )
        doc = item.to_es_doc()
        assert "furnishing" not in doc

    # ── ELSER semantic_text field tests ───────────────────────────────────────

    def test_elser_title_semantic_populated(self):
        """title_semantic must mirror the title field for ELSER inference."""
        item = PropertyItem(
            source="magicbricks",
            source_id="22222222",
            url="https://example.com",
            title="3 BHK Apartment in Whitefield",
        )
        doc = item.to_es_doc()
        assert "title_semantic" in doc
        assert doc["title_semantic"] == "3 BHK Apartment in Whitefield"

    def test_elser_description_semantic_populated(self):
        """description_semantic must mirror description."""
        item = PropertyItem(
            source="99acres",
            source_id="33333333",
            url="https://example.com",
            description="Spacious flat with swimming pool and gym facilities.",
        )
        doc = item.to_es_doc()
        assert "description_semantic" in doc
        assert doc["description_semantic"] == item.description

    def test_elser_amenities_semantic_is_joined_string(self):
        """amenities_semantic must be a space-joined string of the amenities list."""
        item = PropertyItem(
            source="magicbricks",
            source_id="44444444",
            url="https://example.com",
            amenities=["Swimming Pool", "Gym", "Parking", "Clubhouse"],
        )
        doc = item.to_es_doc()
        assert "amenities_semantic" in doc
        assert doc["amenities_semantic"] == "Swimming Pool Gym Parking Clubhouse"
        # Original keyword list must still be present
        assert doc["amenities"] == ["Swimming Pool", "Gym", "Parking", "Clubhouse"]

    def test_elser_address_semantic_populated(self):
        """address_semantic must mirror address."""
        item = PropertyItem(
            source="99acres",
            source_id="55555555",
            url="https://example.com",
            address="12 MG Road, Koramangala, Bangalore 560034",
        )
        doc = item.to_es_doc()
        assert "address_semantic" in doc
        assert doc["address_semantic"] == item.address

    def test_elser_semantic_fields_absent_when_source_empty(self):
        """Semantic fields must NOT appear when the source text is empty/absent."""
        item = PropertyItem(
            source="magicbricks",
            source_id="66666666",
            url="https://example.com",
            # title, description, address all default to ""
            amenities=[],
        )
        doc = item.to_es_doc()
        assert "title_semantic"       not in doc
        assert "description_semantic" not in doc
        assert "amenities_semantic"   not in doc
        assert "address_semantic"     not in doc


class TestDocId:
    def test_deterministic(self):
        id1 = BangalorePropertySpider.make_doc_id("magicbricks", "12345")
        id2 = BangalorePropertySpider.make_doc_id("magicbricks", "12345")
        assert id1 == id2

    def test_different_sources(self):
        id1 = BangalorePropertySpider.make_doc_id("magicbricks", "12345")
        id2 = BangalorePropertySpider.make_doc_id("99acres", "12345")
        assert id1 != id2
