"""
crawler/spiders/magicbricks_spider.py
───────────────────────────────────────
Spider for MagicBricks property listings.

Covers:
  - Whitefield, Bangalore
  - Koramangala, Bangalore

Transaction types: sale + rent

URL pattern:
  Rent  → https://www.magicbricks.com/property-for-rent/residential-real-estate?
              proptype=Multistorey-Apartment,Builder-Floor-Apartment,Penthouse,Studio-Apartment
              &cityName=Bangalore&Area=Whitefield
  Sale  → https://www.magicbricks.com/property-for-sale/residential-real-estate?
              proptype=Multistorey-Apartment,Builder-Floor-Apartment,Penthouse,Studio-Apartment
              &cityName=Bangalore&Area=Whitefield

NOTE: MagicBricks uses Cloudflare/JS rendering for heavy pages.
      This spider targets the lightweight listing API endpoint that
      returns JSON and does not require headless browser execution.
      If the site structure changes, update selectors accordingly.
"""

from __future__ import annotations

import json
import logging
from typing import Iterator, Optional
from urllib.parse import urlencode

import scrapy

from config.areas import AreaConfig
from crawler.items import GeoPoint, PropertyItem
from crawler.spiders.base_spider import BangalorePropertySpider

log = logging.getLogger(__name__)

# Property types to crawl
PROP_TYPES = "Multistorey-Apartment,Builder-Floor-Apartment,Penthouse,Studio-Apartment,Residential-House,Villa"


class MagicBricksSpider(BangalorePropertySpider):
    """Crawls MagicBricks listings for the 2 target Bangalore areas."""

    name = "magicbricks"
    source = "magicbricks"
    allowed_domains = ["magicbricks.com"]

    # Pagination
    PAGE_SIZE = 30

    # ── URL builders ─────────────────────────────────────────────────────────

    def _listing_url(self, area: AreaConfig, tx_type: str, page: int = 1) -> str:
        tx_word = "rent" if tx_type == "rent" else "sale"
        params = {
            "proptype": PROP_TYPES,
            "cityName": "Bangalore",
            "Area": area.magicbricks_slug,
            "page": page,
            "pageSize": self.PAGE_SIZE,
        }
        base = f"https://www.magicbricks.com/property-for-{tx_word}/residential-real-estate"
        return f"{base}?{urlencode(params)}"

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
        )

    # ── Listing page (search results) ─────────────────────────────────────────

    def parse_listing_page(self, response: scrapy.http.Response):
        area: AreaConfig = response.meta["area"]
        tx_type: str = response.meta["tx_type"]
        page: int = response.meta["page"]

        # Cards on the listing/search page
        cards = response.css("div.mb-srp__list article.mb-srp__card")

        if not cards:
            log.warning("[magicbricks] No cards found on page %d — area=%s tx=%s",
                        page, area.name, tx_type)
            return

        log.info("[magicbricks] Page %d → %d cards | area=%s tx=%s",
                 page, len(cards), area.name, tx_type)

        for card in cards:
            listing_url = card.css("a.mb-srp__card--title::attr(href)").get("")
            if listing_url:
                if not listing_url.startswith("http"):
                    listing_url = f"https://www.magicbricks.com{listing_url}"
                yield scrapy.Request(
                    url=listing_url,
                    callback=self.parse_listing,
                    meta={"area": area, "tx_type": tx_type},
                    errback=self.on_error,
                )
            else:
                # Fallback: parse inline card data directly
                item = self._parse_card(card, area, tx_type, response.url)
                if item:
                    yield item

        # Pagination — follow next page if cards were found
        next_page = response.css("a.mb-srp__pagination--next::attr(href)").get()
        if next_page and len(cards) == self.PAGE_SIZE:
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

            # Attempt JSON-LD structured data first (most reliable)
            json_ld = self._try_json_ld(response)

            price_text = (
                response.css("div.mb-ldp__price--val::text").get("")
                or response.css("[data-price]::attr(data-price)").get("")
            )
            price = self.parse_price(price_text)

            area_text = (
                response.css("div.mb-ldp__det--prop__area span::text").get("")
                or response.css("[data-area]::text").get("")
            )
            area_sqft = self.parse_area_sqft(area_text)

            bedrooms_text = response.css(
                "div.mb-ldp__det--prop__bhk::text, [data-bedrooms]::text"
            ).get("")
            bedrooms = self._extract_int(bedrooms_text)

            title = self.clean_text(
                response.css("h1.mb-ldp__info--name::text, h1.page-title::text").get("")
            )
            description = self.clean_text(
                " ".join(response.css("div.mb-ldp__desc--text *::text").getall())
            )
            posted_by = self.clean_text(
                response.css("span.mb-ldp__posted-by--type::text").get("")
            ).lower()
            amenities = [
                self.clean_text(a)
                for a in response.css("li.mb-ldp__amenities--item::text").getall()
                if a.strip()
            ]
            images = response.css(
                "div.mb-ldp__media img::attr(src), div.mb-ldp__gallery img::attr(src)"
            ).getall()

            furnishing = self.clean_text(
                response.css("[data-furnishing]::text, .furnishing::text").get("")
            )

            # Geo from JSON-LD or page meta
            geo = self._extract_geo(response, json_ld)

            item = PropertyItem(
                source=self.source,
                source_id=source_id,
                url=response.url,
                area=area.name,
                city=area.city,
                state="Karnataka",
                title=title,
                description=description,
                transaction_type=tx_type,
                property_type="apartment",
                posted_by=posted_by,
                area_sqft=area_sqft,
                bedrooms=bedrooms,
                price=price,
                furnishing=furnishing,
                amenities=amenities,
                images=images[:10],
                geo=geo or GeoPoint(lat=area.latitude, lon=area.longitude),
            )
            return item

        except Exception as exc:
            log.exception("[magicbricks] Failed to parse %s: %s", response.url, exc)
            return None

    # ── Inline card fallback ──────────────────────────────────────────────────

    def _parse_card(
        self,
        card: scrapy.Selector,
        area: AreaConfig,
        tx_type: str,
        page_url: str,
    ) -> Optional[PropertyItem]:
        """Extract data directly from a search result card (no detail page visit)."""
        try:
            title = self.clean_text(card.css("h2.mb-srp__card--title::text").get(""))
            price_text = card.css("span.mb-srp__card__price--amount::text").get("")
            price = self.parse_price(price_text)
            area_text = card.css("span[data-summary='super-area']::text").get("")
            area_sqft = self.parse_area_sqft(area_text)
            bedrooms_text = card.css("span[data-summary='bedroom']::text").get("")
            bedrooms = self._extract_int(bedrooms_text)
            source_id = card.attrib.get("data-id", "")

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
                property_type="apartment",
                area_sqft=area_sqft,
                bedrooms=bedrooms,
                price=price,
                geo=GeoPoint(lat=area.latitude, lon=area.longitude),
            )
        except Exception as exc:
            log.debug("[magicbricks] Card parse error: %s", exc)
            return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extract_source_id(self, url: str) -> str:
        """Pull numeric property ID from MagicBricks URL."""
        import re
        match = re.search(r"-(\d{7,12})(?:\.html)?$", url)
        return match.group(1) if match else url.split("/")[-1]

    def _try_json_ld(self, response: scrapy.http.Response) -> Optional[dict]:
        """Try to parse JSON-LD structured data from the page."""
        for script in response.css('script[type="application/ld+json"]::text').getall():
            try:
                data = json.loads(script)
                if isinstance(data, dict) and data.get("@type") in (
                    "Residence", "House", "Apartment", "RealEstateListing"
                ):
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

        lat = response.css("[data-lat]::attr(data-lat)").get()
        lon = response.css("[data-lon]::attr(data-lon), [data-lng]::attr(data-lng)").get()
        if lat and lon:
            return GeoPoint(lat=float(lat), lon=float(lon))
        return None

    @staticmethod
    def _extract_int(text: str) -> Optional[int]:
        import re
        match = re.search(r"\d+", text or "")
        return int(match.group()) if match else None

    def on_error(self, failure):
        log.error("[magicbricks] Request failed: %s", failure.value)
