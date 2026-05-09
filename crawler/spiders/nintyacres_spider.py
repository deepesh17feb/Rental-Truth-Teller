"""
crawler/spiders/nintyacres_spider.py
──────────────────────────────────────
Spider for 99acres property listings.

Covers:
  - Whitefield, Bangalore
  - Koramangala, Bangalore

Transaction types: sale + rent

URL pattern:
  Rent  → https://www.99acres.com/property-for-rent-in-whitefield-bangalore-ffid-P
  Sale  → https://www.99acres.com/property-for-sale-in-whitefield-bangalore-ffid-P

NOTE: 99acres uses server-side rendered HTML pages with standard
      pagination query params. This spider targets the HTML response.
      Update CSS/XPath selectors if the site layout changes.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Iterator, Optional
from urllib.parse import urlencode, urlparse, parse_qs, urljoin

import scrapy

from config.areas import AreaConfig
from crawler.items import GeoPoint, PropertyItem
from crawler.spiders.base_spider import BangalorePropertySpider

log = logging.getLogger(__name__)


class NinetyAcresSpider(BangalorePropertySpider):
    """Crawls 99acres listings for the 2 target Bangalore areas."""

    name = "99acres"
    source = "99acres"
    allowed_domains = ["99acres.com"]

    PAGE_SIZE = 25  # 99acres shows ~25 per page

    # ── URL builders ─────────────────────────────────────────────────────────

    def _listing_url(self, area: AreaConfig, tx_type: str, page: int = 1) -> str:
        """
        99acres uses SEO-friendly URLs.
        Example: https://www.99acres.com/property-for-rent-in-whitefield-bangalore-ffid-P?page=2
        """
        tx_word = "rent" if tx_type == "rent" else "sale"
        area_slug = area.nintyacres_slug  # e.g. "whitefield-bangalore"
        base = (
            f"https://www.99acres.com/property-for-{tx_word}-in-{area_slug}-ffid-P"
        )
        if page > 1:
            return f"{base}?page={page}"
        return base

    # ── Entry-point for each area ─────────────────────────────────────────────

    def start_requests_for_area(
        self, area: AreaConfig, tx_type: str
    ) -> Iterator[scrapy.Request]:
        url = self._listing_url(area, tx_type, page=1)
        yield scrapy.Request(
            url=url,
            callback=self.parse_listing_page,
            meta={"area": area, "tx_type": tx_type, "page": 1},
            errback=self.on_error,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )

    # ── Listing page (search results) ─────────────────────────────────────────

    def parse_listing_page(self, response: scrapy.http.Response):
        area: AreaConfig = response.meta["area"]
        tx_type: str = response.meta["tx_type"]
        page: int = response.meta["page"]

        # 99acres listing cards
        cards = response.css(
            "div[data-label='CARD_WRAPPER'], "
            "div.srpTuple__TupleWrapper, "
            "article.PropertyCard"
        )

        if not cards:
            log.warning("[99acres] No cards found on page %d — area=%s tx=%s",
                        page, area.name, tx_type)
            return

        log.info("[99acres] Page %d → %d cards | area=%s tx=%s",
                 page, len(cards), area.name, tx_type)

        for card in cards:
            # Try to get the detail page URL
            detail_href = (
                card.css("a.srpTuple__propType::attr(href)").get()
                or card.css("a[data-label='TUPLE_HEADER_LINK']::attr(href)").get()
                or card.css("a.PropertyCard__link::attr(href)").get()
            )
            if detail_href:
                detail_url = urljoin("https://www.99acres.com", detail_href)
                yield scrapy.Request(
                    url=detail_url,
                    callback=self.parse_listing,
                    meta={"area": area, "tx_type": tx_type},
                    errback=self.on_error,
                )
            else:
                # Parse inline from card
                item = self._parse_card(card, area, tx_type, response.url)
                if item:
                    yield item

        # Pagination — stop if fewer cards than PAGE_SIZE (last page)
        if len(cards) >= self.PAGE_SIZE:
            next_url = self._listing_url(area, tx_type, page + 1)
            yield scrapy.Request(
                url=next_url,
                callback=self.parse_listing_page,
                meta={"area": area, "tx_type": tx_type, "page": page + 1},
                errback=self.on_error,
            )

    # ── Detail page ───────────────────────────────────────────────────────────

    def parse_listing(self, response: scrapy.http.Response) -> Optional[PropertyItem]:
        area: AreaConfig = response.meta["area"]
        tx_type: str = response.meta["tx_type"]

        try:
            source_id = self._extract_source_id(response.url)

            # Try JSON-LD
            json_ld = self._try_json_ld(response)

            # Price
            price_text = (
                response.css(
                    "span.pdp__price, "
                    "[data-price]::text, "
                    "span.price-text::text"
                ).get("")
            )
            price = self.parse_price(price_text)

            # Area sqft
            area_text = (
                response.css(
                    "div.pdpAmen__detailsText:contains('sq') span::text,"
                    "span[data-label='AREA']::text"
                ).get("")
            )
            area_sqft = self.parse_area_sqft(area_text)

            # Bedrooms
            bedroom_text = (
                response.css(
                    "span.pdpAmen__detailsText:contains('BHK')::text,"
                    "span[data-label='BHK']::text"
                ).get("")
                or response.css("h1.pdp__propType::text").get("")
            )
            bedrooms = self._extract_bhk(bedroom_text)

            title = self.clean_text(
                response.css(
                    "h1.pdp__title::text, "
                    "h1.propertyDetailPage__title::text, "
                    "h1.PropertyTitle::text"
                ).get("")
            )

            description = self.clean_text(
                " ".join(
                    response.css(
                        "div.descBox__text *::text, "
                        "div.pdp__description *::text"
                    ).getall()
                )
            )

            # Amenities
            amenities = [
                self.clean_text(a)
                for a in response.css(
                    "li.amtList__amentText::text, "
                    "span.ameniTag::text"
                ).getall()
                if a.strip()
            ]

            # Furnishing status
            furnishing = self.clean_text(
                response.css(
                    "span[data-label='FURNISHING']::text, "
                    "li:contains('Furnished') span::text"
                ).get("")
            )

            # Posted by
            posted_by = self.clean_text(
                response.css(
                    "span.agentProfile__nameText::text, "
                    "span.ownerBlock__ownerName::text"
                ).get("")
            )

            # Images
            images = response.css(
                "div.pdp__gallery img::attr(src), "
                "div.galleryMedia img::attr(src)"
            ).getall()

            # Floors
            floor_text = response.css(
                "span[data-label='FLOOR']::text, li:contains('Floor') span::text"
            ).get("")
            floor, total_floors = self._parse_floors(floor_text)

            # Geo
            geo = self._extract_geo(response, json_ld) or GeoPoint(
                lat=area.latitude, lon=area.longitude
            )

            # Deposit (rent only)
            deposit_text = response.css(
                "span[data-label='DEPOSIT']::text, "
                "div:contains('Security Deposit') span::text"
            ).get("")
            deposit = self.parse_price(deposit_text) if tx_type == "rent" else None

            # Posted date
            posted_date = self.clean_text(
                response.css("span.pdp__updatedDate::text").get("")
            )

            return PropertyItem(
                source=self.source,
                source_id=source_id,
                url=response.url,
                area=area.name,
                city=area.city,
                state="Karnataka",
                title=title,
                description=description,
                transaction_type=tx_type,
                property_type=self._detect_property_type(title),
                posted_by=posted_by.lower() or "unknown",
                posted_date=posted_date or None,
                area_sqft=area_sqft,
                bedrooms=bedrooms,
                floor=floor,
                total_floors=total_floors,
                price=price,
                deposit=deposit,
                furnishing=furnishing.lower(),
                amenities=amenities,
                images=images[:10],
                geo=geo,
            )

        except Exception as exc:
            log.exception("[99acres] Failed to parse %s: %s", response.url, exc)
            return None

    # ── Inline card fallback ──────────────────────────────────────────────────

    def _parse_card(
        self,
        card: scrapy.Selector,
        area: AreaConfig,
        tx_type: str,
        page_url: str,
    ) -> Optional[PropertyItem]:
        try:
            title = self.clean_text(
                card.css(
                    "span.srpTuple__propertyName::text, "
                    "div.PropertyCard__title::text"
                ).get("")
            )
            price_text = card.css(
                "span.srpTuple__priceDetails::text, "
                "div.price::text"
            ).get("")
            price = self.parse_price(price_text)
            bedrooms_text = card.css(
                "span.srpTuple__propType::text, "
                "span.bhkBlock::text"
            ).get("")
            bedrooms = self._extract_bhk(bedrooms_text)
            area_text = card.css("span[data-label='AREA']::text").get("")
            area_sqft = self.parse_area_sqft(area_text)
            source_id = card.attrib.get("data-id", "").strip()

            if not source_id or not title:
                return None

            return PropertyItem(
                source=self.source,
                source_id=source_id,
                url=page_url,
                area=area.name,
                city=area.city,
                state="Karnataka",
                title=title,
                transaction_type=tx_type,
                property_type=self._detect_property_type(title),
                bedrooms=bedrooms,
                area_sqft=area_sqft,
                price=price,
                geo=GeoPoint(lat=area.latitude, lon=area.longitude),
            )
        except Exception as exc:
            log.debug("[99acres] Card parse error: %s", exc)
            return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extract_source_id(self, url: str) -> str:
        match = re.search(r"-(\d{7,14})(?:\.html)?$", url)
        return match.group(1) if match else url.split("/")[-1].split("?")[0]

    def _extract_bhk(self, text: str) -> Optional[int]:
        """Extract bedroom count from '3 BHK', '3BHK', '3 Bedroom' strings."""
        if not text:
            return None
        match = re.search(r"(\d+)\s*(?:BHK|bhk|bedroom|Bedroom)", text)
        return int(match.group(1)) if match else None

    def _parse_floors(self, text: str) -> tuple[Optional[int], Optional[int]]:
        """Parse '3 out of 10' or '3/10' floor strings."""
        if not text:
            return None, None
        parts = re.findall(r"\d+", text)
        if len(parts) >= 2:
            return int(parts[0]), int(parts[1])
        if len(parts) == 1:
            return int(parts[0]), None
        return None, None

    def _detect_property_type(self, title: str) -> str:
        title_lower = (title or "").lower()
        if "villa" in title_lower:
            return "villa"
        if "plot" in title_lower or "land" in title_lower:
            return "plot"
        if "office" in title_lower or "commercial" in title_lower:
            return "commercial"
        if "independent house" in title_lower:
            return "independent_house"
        return "apartment"

    def _try_json_ld(self, response: scrapy.http.Response) -> Optional[dict]:
        for script in response.css('script[type="application/ld+json"]::text').getall():
            try:
                data = json.loads(script)
                if isinstance(data, dict) and "@type" in data:
                    return data
            except json.JSONDecodeError:
                continue
        return None

    def _extract_geo(
        self,
        response: scrapy.http.Response,
        json_ld: Optional[dict],
    ) -> Optional[GeoPoint]:
        if json_ld:
            geo = json_ld.get("geo") or {}
            lat = geo.get("latitude")
            lon = geo.get("longitude")
            if lat and lon:
                return GeoPoint(lat=float(lat), lon=float(lon))

        lat = (
            response.css("[data-lat]::attr(data-lat)").get()
            or response.css("[data-latitude]::attr(data-latitude)").get()
        )
        lon = (
            response.css("[data-lng]::attr(data-lng)").get()
            or response.css("[data-longitude]::attr(data-longitude)").get()
        )
        if lat and lon:
            return GeoPoint(lat=float(lat), lon=float(lon))
        return None

    def on_error(self, failure):
        log.error("[99acres] Request failed: %s", failure.value)
