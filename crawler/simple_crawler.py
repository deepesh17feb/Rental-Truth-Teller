"""
crawler/simple_crawler.py
──────────────────────────
Pure-requests property crawler for Bangalore — no Scrapy required.

Works with the packages already available on the Walmart dev machine:
  • requests       — HTTP
  • re / html.parser — HTML + JSON extraction (Python stdlib)
  • elasticsearch  — indexing into Elastic Cloud

Covers:
  Source 1: MagicBricks  (magicbricks.com)
  Source 2: 99acres       (99acres.com)

  Areas : Whitefield, Koramangala (driven by config/areas.py)
  Tx    : rent + sale
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from html.parser import HTMLParser
from typing import Generator, List, Optional
from urllib.parse import urljoin, urlencode, quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.areas import TARGET_AREAS, AreaConfig
from config.settings import config
from crawler.items import GeoPoint, PropertyItem

log = logging.getLogger(__name__)

# ── Proxy (Walmart corporate network) ────────────────────────────────────────
_PROXY_URL = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
_PROXIES   = {"http": _PROXY_URL, "https": _PROXY_URL} if _PROXY_URL else {}

# ── Headers ───────────────────────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
}


# ─────────────────────────────────────────────────────────────────────────────
# Shared HTTP session
# ─────────────────────────────────────────────────────────────────────────────

def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_HEADERS)
    if _PROXIES:
        session.proxies.update(_PROXIES)
        log.debug("HTTP session using proxy: %s", _PROXY_URL)

    retry = Retry(
        total=config.CRAWL_MAX_RETRIES,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://",  adapter)

    # Establish cookies by hitting home page
    try:
        session.get("https://www.magicbricks.com/", timeout=10)
    except:
        pass

    return session


# ─────────────────────────────────────────────────────────────────────────────
# Shared utilities
# ─────────────────────────────────────────────────────────────────────────────

def _make_doc_id(source: str, source_id: str) -> str:
    return hashlib.sha256(f"{source}::{source_id}".encode()).hexdigest()


from crawler.utils.parsers import parse_price as _parse_price, parse_area_sqft as _parse_sqft, extract_bhk as _extract_bhk, clean_text as _clean


def _extract_json_from_script(html: str, var_names: List[str]) -> Optional[dict]:
    """
    Extract a JS window variable embedded in a <script> tag.
    Tries: window.__STATE__ = {...}, window.__DATA__ = {...}, etc.
    """
    for var in var_names:
        pattern = rf'(?:window\.)?{re.escape(var)}\s*=\s*(\{{.*?\}})\s*;'
        m = re.search(pattern, html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# MagicBricks crawler
# ─────────────────────────────────────────────────────────────────────────────

class MagicBricksCrawler:
    """
    Crawls MagicBricks listing search pages for Bangalore properties.

    Strategy:
      1. Hit the search page for each area × transaction type.
      2. Extract JSON embedded in <script> tags (window.__REDUX_STATE__ or
         window.BROWSER_INITIAL_STATE or similar patterns).
      3. If JSON unavailable, fall back to regex on the raw HTML cards.
      4. Yield PropertyItem for each listing found.
    """

    SOURCE = "magicbricks"

    # MagicBricks search API (returns JSON — more reliable than HTML parsing)
    _SEARCH_API = (
        "https://www.magicbricks.com/mbsrp/propertySearch.html"
        "?editSearch=Y"
        "&category={category}"
        "&projNameLocality={locality}"
        "&cityName=Bangalore"
        "&proptype=MULT,BILD,LAND,PENT,MECO,RESO"
        "&isNRISearch=false"
        "&offset={offset}"
        "&count=30"
        "&sortby=1"
    )

    def __init__(self, session: requests.Session):
        self.session = session

    def crawl(self, area: AreaConfig, tx_type: str) -> Generator[PropertyItem, None, None]:
        category = "S" if tx_type == "sale" else "R"
        
        # If area has specific societies, crawl them one by one.
        # Otherwise, crawl the entire area.
        localities = [area.magicbricks_slug]
        if area.societies:
            localities = area.societies

        for loc_name in localities:
            locality  = quote(loc_name)
            offset    = 0
            page      = 1

            while True:
                url = self._SEARCH_API.format(
                    category=category, locality=locality, offset=offset
                )
                log.info("[MagicBricks] Page %d | %s | %s", page, loc_name, tx_type)

                try:
                    # Add Referer to headers
                    headers = {
                        "Referer": "https://www.magicbricks.com/property-for-rent/residential-real-estate?cityName=Bangalore"
                    }
                    resp = self.session.get(url, headers=headers, timeout=config.CRAWL_DOWNLOAD_TIMEOUT)
                    resp.raise_for_status()
                except requests.RequestException as exc:
                    log.error("[MagicBricks] Request failed for %s: %s", loc_name, exc)
                    break

                # Try JSON response first (the API sometimes returns JSON directly)
                try:
                    data = resp.json()
                    listings = (
                        data.get("propertyList")
                        or data.get("propList")
                        or data.get("results")
                        or []
                    )
                    if listings:
                        log.info("[MagicBricks] JSON API → %d listings for %s", len(listings), loc_name)
                        for raw in listings:
                            item = self._parse_json_listing(raw, area, tx_type)
                            if item:
                                yield item

                        if len(listings) < 30:
                            break
                        offset += 30
                        page   += 1
                        time.sleep(config.CRAWL_DELAY_SECONDS)
                        continue
                except ValueError:
                    pass  # Not JSON — fall through to HTML

                # HTML fallback: extract embedded JS state
                html = resp.text
                items = list(self._parse_html_page(html, area, tx_type, url))
                log.info("[MagicBricks] HTML fallback → %d items for %s", len(items), loc_name)
                yield from items

                # Pagination via HTML — look for next offset
                next_m = re.search(r'"nextOffset"\s*:\s*(\d+)', html)
                if not next_m or not items:
                    break
                offset = int(next_m.group(1))
                page  += 1
                time.sleep(config.CRAWL_DELAY_SECONDS)

    def _parse_json_listing(
        self, raw: dict, area: AreaConfig, tx_type: str
    ) -> Optional[PropertyItem]:
        try:
            source_id = str(
                raw.get("propId") or raw.get("id") or raw.get("propertyId") or ""
            )
            if not source_id:
                return None

            price_raw = (
                raw.get("priceDisplay")
                or raw.get("price")
                or raw.get("displayPrice")
                or ""
            )

            return PropertyItem(
                source    = self.SOURCE,
                source_id = source_id,
                url       = raw.get("propUrl") or raw.get("url") or "",
                area      = area.name,
                city      = area.city,
                state     = "Karnataka",
                title     = _clean(raw.get("propHeading") or raw.get("title") or ""),
                description = _clean(raw.get("description") or ""),
                transaction_type = tx_type,
                property_type    = self._map_type(
                    raw.get("propType") or raw.get("propertyType") or ""
                ),
                posted_by    = _clean(raw.get("contactType") or "").lower(),
                bedrooms     = self._safe_int(raw.get("bedroom") or raw.get("bhk")),
                bathrooms    = self._safe_int(raw.get("bathroom")),
                area_sqft    = self._safe_float(raw.get("builtUpArea") or raw.get("area")),
                price        = _parse_price(str(price_raw)),
                furnishing   = _clean(raw.get("furnishing") or "").lower(),
                amenities    = raw.get("amenities") or [],
                geo          = self._extract_geo(raw, area),
            )
        except Exception as exc:
            log.debug("[MagicBricks] JSON parse error: %s", exc)
            return None

    def _parse_html_page(
        self, html: str, area: AreaConfig, tx_type: str, page_url: str
    ) -> Generator[PropertyItem, None, None]:
        """Extract listings from raw HTML using regex patterns."""

        # Pattern 1: JSON blobs in script tags
        data = _extract_json_from_script(
            html, ["BROWSER_INITIAL_STATE", "__REDUX_STATE__", "__APP_DATA__",
                   "propertyList", "INITIAL_STATE"]
        )
        if data:
            listings = (
                self._dig(data, "propertySearch", "propertyList")
                or self._dig(data, "srpProps", "propertyList")
                or []
            )
            for raw in listings:
                item = self._parse_json_listing(raw, area, tx_type)
                if item:
                    yield item
            if listings:
                return

        # Pattern 2: Inline property data via regex on HTML
        # MagicBricks embeds: data-propid="..." data-price="..." etc.
        ids_found = set()
        for m in re.finditer(r'data-propid=["\'](\d+)["\']', html):
            prop_id = m.group(1)
            if prop_id in ids_found:
                continue
            ids_found.add(prop_id)

            # Extract a window around this match for context
            start = max(0, m.start() - 500)
            end   = min(len(html), m.end() + 1500)
            chunk = html[start:end]

            price_m = re.search(r'data-price=["\']([^"\']+)["\']', chunk)
            title_m = re.search(r'class="[^"]*mb-srp__card--title[^"]*"[^>]*>([^<]+)', chunk)
            bhk_m   = re.search(r'(\d+)\s*BHK', chunk)
            area_m  = re.search(r'(\d[\d,]*\.?\d*)\s*(?:sq\.?\s*ft|Sq\.?Ft)', chunk, re.IGNORECASE)
            url_m   = re.search(r'href=["\'](/property-[^"\']+)["\']', chunk)

            yield PropertyItem(
                source    = self.SOURCE,
                source_id = prop_id,
                url       = urljoin("https://www.magicbricks.com", url_m.group(1)) if url_m else page_url,
                area      = area.name,
                city      = area.city,
                state     = "Karnataka",
                title     = _clean(title_m.group(1)) if title_m else f"Property in {area.name}",
                transaction_type = tx_type,
                property_type    = "apartment",
                bedrooms  = int(bhk_m.group(1)) if bhk_m else None,
                area_sqft = _parse_sqft(area_m.group(0)) if area_m else None,
                price     = _parse_price(price_m.group(1)) if price_m else None,
                geo       = GeoPoint(lat=area.latitude, lon=area.longitude),
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _map_type(raw: str) -> str:
        raw = raw.lower()
        if "villa" in raw:      return "villa"
        if "plot" in raw:       return "plot"
        if "house" in raw:      return "independent_house"
        if "commercial" in raw: return "commercial"
        return "apartment"

    @staticmethod
    def _safe_int(val) -> Optional[int]:
        try:   return int(val) if val is not None else None
        except: return None

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        try:   return float(val) if val is not None else None
        except: return None

    @staticmethod
    def _extract_geo(raw: dict, area: AreaConfig) -> GeoPoint:
        try:
            lat = float(raw.get("latitude") or raw.get("lat") or area.latitude)
            lon = float(raw.get("longitude") or raw.get("lng") or area.longitude)
            return GeoPoint(lat=lat, lon=lon)
        except:
            return GeoPoint(lat=area.latitude, lon=area.longitude)

    @staticmethod
    def _dig(data: dict, *keys) -> Optional[list]:
        for key in keys:
            if isinstance(data, dict):
                data = data.get(key)
            else:
                return None
        return data if isinstance(data, list) else None


# ─────────────────────────────────────────────────────────────────────────────
# 99acres crawler
# ─────────────────────────────────────────────────────────────────────────────

class NinetyAcresCrawler:
    """
    Crawls 99acres listing search pages for Bangalore properties.

    Strategy:
      1. Hit the SEO-friendly search page for each area × tx type.
      2. Extract __INITIAL_STATE__ JSON embedded in a <script> tag.
      3. Fall back to regex on HTML card elements if JSON unavailable.
    """

    SOURCE = "99acres"

    def __init__(self, session: requests.Session):
        self.session = session

    def _search_url(self, area: AreaConfig, tx_type: str, page: int = 1) -> str:
        tx  = "rent" if tx_type == "rent" else "sale"
        slg = area.nintyacres_slug
        url = f"https://www.99acres.com/property-for-{tx}-in-{slg}-ffid-P"
        return f"{url}?page={page}" if page > 1 else url

    def crawl(self, area: AreaConfig, tx_type: str) -> Generator[PropertyItem, None, None]:
        page = 1
        while True:
            url = self._search_url(area, tx_type, page)
            log.info("[99acres] Page %d | area=%s tx=%s", page, area.name, tx_type)

            try:
                resp = self.session.get(url, timeout=config.CRAWL_DOWNLOAD_TIMEOUT)
                resp.raise_for_status()
            except requests.RequestException as exc:
                log.error("[99acres] Request failed: %s", exc)
                break

            html    = resp.text
            found   = list(self._parse_page(html, area, tx_type, url))
            log.info("[99acres] → %d items on page %d", len(found), page)
            yield from found

            if not found:
                break

            # 99acres uses 25 per page
            if len(found) < 20:
                break

            page += 1
            time.sleep(config.CRAWL_DELAY_SECONDS)

    def _parse_page(
        self, html: str, area: AreaConfig, tx_type: str, page_url: str
    ) -> Generator[PropertyItem, None, None]:

        # ── Attempt 1: __INITIAL_STATE__ JSON in <script> ─────────────────────
        state = _extract_json_from_script(
            html,
            ["__INITIAL_STATE__", "INITIAL_STATE", "__APP_STATE__",
             "__PRELOADED_STATE__", "pageState"]
        )
        if state:
            listings = (
                self._dig_listings(state, "srp", "listingData", "propertyList")
                or self._dig_listings(state, "SEARCH_RESULT", "propertyList")
                or self._dig_listings(state, "propertyList")
                or []
            )
            if listings:
                log.debug("[99acres] JSON state → %d listings", len(listings))
                for raw in listings:
                    item = self._parse_json_listing(raw, area, tx_type)
                    if item:
                        yield item
                return

        # ── Attempt 2: JSON blobs in script tags with property data ───────────
        for m in re.finditer(
            r'<script[^>]*>\s*(\{["\'](?:propId|propertyId|prop_id)["\'].*?\})\s*</script>',
            html, re.DOTALL
        ):
            try:
                raw  = json.loads(m.group(1))
                item = self._parse_json_listing(raw, area, tx_type)
                if item:
                    yield item
            except json.JSONDecodeError:
                pass

        # ── Attempt 3: HTML regex fallback ────────────────────────────────────
        ids_found: set[str] = set()

        for m in re.finditer(
            r'data-(?:id|propid|property-id)=["\'](\d+)["\']', html
        ):
            prop_id = m.group(1)
            if prop_id in ids_found:
                continue
            ids_found.add(prop_id)

            start = max(0, m.start() - 200)
            end   = min(len(html), m.end() + 2000)
            chunk = html[start:end]

            price_m = re.search(
                r'(?:₹|Rs\.?)\s*[\d,]+(?:\.\d+)?\s*(?:Cr|Lac|Lakh|K)?', chunk, re.IGNORECASE
            )
            bhk_m  = re.search(r'(\d+)\s*BHK', chunk, re.IGNORECASE)
            area_m = re.search(r'(\d[\d,]*)\s*(?:sq\.?\s*ft|sqft)', chunk, re.IGNORECASE)
            title_m= re.search(
                r'(?:class="[^"]*(?:title|heading|name)[^"]*"[^>]*>)([^<]{10,120})', chunk
            )
            url_m  = re.search(r'href=["\'](/property-for-[^"\'?]+)["\']', chunk)

            yield PropertyItem(
                source    = self.SOURCE,
                source_id = prop_id,
                url       = urljoin("https://www.99acres.com", url_m.group(1)) if url_m else page_url,
                area      = area.name,
                city      = area.city,
                state     = "Karnataka",
                title     = _clean(title_m.group(1)) if title_m else f"Property in {area.name}",
                transaction_type = tx_type,
                property_type    = "apartment",
                bedrooms  = int(bhk_m.group(1)) if bhk_m else None,
                area_sqft = _parse_sqft(area_m.group(0)) if area_m else None,
                price     = _parse_price(price_m.group(0)) if price_m else None,
                geo       = GeoPoint(lat=area.latitude, lon=area.longitude),
            )

    def _parse_json_listing(
        self, raw: dict, area: AreaConfig, tx_type: str
    ) -> Optional[PropertyItem]:
        try:
            source_id = str(
                raw.get("propId") or raw.get("propertyId")
                or raw.get("prop_id") or raw.get("id") or ""
            )
            if not source_id:
                return None

            price_raw = (
                raw.get("price") or raw.get("displayPrice")
                or raw.get("priceDisplay") or ""
            )

            amenities_raw = raw.get("amenities") or raw.get("facilities") or []
            if isinstance(amenities_raw, dict):
                amenities_raw = list(amenities_raw.keys())

            geo_lat = raw.get("latitude") or raw.get("lat") or area.latitude
            geo_lon = raw.get("longitude") or raw.get("lng") or area.longitude

            return PropertyItem(
                source    = self.SOURCE,
                source_id = source_id,
                url       = raw.get("propertyUrl") or raw.get("url") or "",
                area      = area.name,
                city      = area.city,
                state     = "Karnataka",
                title     = _clean(
                    raw.get("propertyName") or raw.get("title")
                    or raw.get("heading") or ""
                ),
                description = _clean(raw.get("description") or ""),
                transaction_type = tx_type,
                property_type    = self._map_type(
                    raw.get("propertyType") or raw.get("prop_type") or ""
                ),
                posted_by  = _clean(raw.get("postedBy") or raw.get("contactType") or "").lower(),
                bedrooms   = self._safe_int(raw.get("bedroom") or raw.get("bhk")),
                bathrooms  = self._safe_int(raw.get("bathroom")),
                area_sqft  = self._safe_float(
                    raw.get("builtUpArea") or raw.get("carpetArea") or raw.get("area")
                ),
                price      = _parse_price(str(price_raw)),
                deposit    = _parse_price(str(raw.get("deposit") or "")) if tx_type == "rent" else None,
                furnishing = _clean(raw.get("furnishStatus") or raw.get("furnishing") or "").lower(),
                amenities  = [str(a) for a in amenities_raw if a],
                geo        = GeoPoint(lat=float(geo_lat), lon=float(geo_lon)),
            )
        except Exception as exc:
            log.debug("[99acres] JSON parse error: %s", exc)
            return None

    @staticmethod
    def _map_type(raw: str) -> str:
        raw = str(raw).lower()
        if "villa"   in raw: return "villa"
        if "plot"    in raw: return "plot"
        if "house"   in raw: return "independent_house"
        if "office"  in raw: return "commercial"
        return "apartment"

    @staticmethod
    def _safe_int(val) -> Optional[int]:
        try:   return int(val) if val is not None else None
        except: return None

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        try:   return float(val) if val is not None else None
        except: return None

    @staticmethod
    def _dig_listings(data: dict, *keys) -> Optional[list]:
        for key in keys:
            if isinstance(data, dict):
                data = data.get(key)
            else:
                return None
        return data if isinstance(data, list) else None


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class BangaloreCrawler:
    """
    Top-level orchestrator.
    Drives both crawlers across all configured areas and transaction types.
    """

    def __init__(self):
        self.session = _build_session()
        self.mb      = MagicBricksCrawler(self.session)
        self.na      = NinetyAcresCrawler(self.session)

    def crawl(self) -> Generator[PropertyItem, None, None]:
        tx_types = (
            ["rent", "sale"]
            if config.TRANSACTION_TYPE == "both"
            else [config.TRANSACTION_TYPE]
        )

        for area_key, area in TARGET_AREAS.items():
            log.info("=" * 55)
            log.info("Area: %s", area.name)
            log.info("=" * 55)

            for tx_type in tx_types:
                log.info("── MagicBricks | %s | %s", area.name, tx_type)
                yield from self.mb.crawl(area, tx_type)
                time.sleep(config.CRAWL_DELAY_SECONDS)

                log.info("── 99acres | %s | %s", area.name, tx_type)
                yield from self.na.crawl(area, tx_type)
                time.sleep(config.CRAWL_DELAY_SECONDS)
