"""
scripts/run_browser_crawl.py
──────────────────────────────
Browser-based crawler using Playwright to bypass anti-bot measures.

Usage:
    python3 scripts/run_browser_crawl.py --area indiranagar --source mb
"""

import os
import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from playwright.sync_api import sync_playwright

# ── Project root on sys.path ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.areas import TARGET_AREAS, AreaConfig
from crawler.items import PropertyItem, GeoPoint

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("browser_crawl")

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

class MagicBricksBrowserCrawler:
    def __init__(self, headless: bool = True, slow_mo: int = 0):
        self.headless = headless
        self.slow_mo = slow_mo

    def crawl(self, area: AreaConfig, tx_type: str) -> Generator[PropertyItem, None, None]:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        proxy = {"server": proxy_url} if proxy_url else None
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, slow_mo=self.slow_mo, proxy=proxy)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # Test connectivity
            try:
                page.goto("https://www.google.com", timeout=30000)
                log.info("[Browser-Test] Google title: %s", page.title())
            except Exception as e:
                log.error("[Browser-Test] Failed to reach Google: %s", e)

            category = "rent" if tx_type == "rent" else "sale"
            
            # Always include the area slug itself
            localities = [area.magicbricks_slug]
            if area.societies:
                localities.extend(area.societies)

            for loc_name in localities:
                log.info("[MagicBricks-Browser] Starting %s | %s", loc_name, tx_type)
                
                # Use a more robust search URL
                url = f"https://www.magicbricks.com/property-for-{category}/residential-real-estate?cityName=Bangalore&localityName={loc_name.replace(' ', '%20')}"
                
                try:
                    page.goto(url, wait_until="networkidle", timeout=60000)
                    time.sleep(5) # Wait for JS
                    
                    log.info("[MagicBricks-Browser] Page title: %s", page.title())
                    if "Access Denied" in page.title() or "Cloudflare" in page.content():
                        log.warning("[MagicBricks-Browser] Blocked by anti-bot")
                    debug_path = OUTPUT_DIR / f"debug_{loc_name.replace(' ', '_')}_{ts}.png"
                    page.screenshot(path=str(debug_path))
                    log.info("[MagicBricks-Browser] Saved debug screenshot to %s", debug_path)

                    # Extract cards
                    # Try a broader selector first
                    cards = page.query_selector_all("article.mb-srp__card")
                    if not cards:
                        # Try another common selector
                        cards = page.query_selector_all(".m-srp-card")
                    
                    log.info("[MagicBricks-Browser] Found %d cards for %s", len(cards), loc_name)

                    for card in cards:
                        item = self._parse_card(card, area, tx_type)
                        if item:
                            yield item

                except Exception as exc:
                    log.error("[MagicBricks-Browser] Error crawling %s: %s", loc_name, exc)
                
            browser.close()

    def _parse_card(self, card, area: AreaConfig, tx_type: str) -> Optional[PropertyItem]:
        try:
            title_el = card.query_selector("h2.mb-srp__card--title")
            title = title_el.inner_text() if title_el else ""
            
            price_el = card.query_selector("div.mb-srp__card__price--amount")
            price_text = price_el.inner_text() if price_el else ""
            
            # Use utility from simple_crawler if possible, but let's re-implement basic version for now
            price = self._parse_price(price_text)
            
            source_id = card.get_attribute("id") or ""
            
            if not title or not source_id:
                return None

            return PropertyItem(
                source="magicbricks",
                source_id=source_id,
                url="https://www.magicbricks.com", # Simplified
                area=area.name,
                city=area.city,
                state="Karnataka",
                title=title.strip(),
                transaction_type=tx_type,
                property_type="apartment",
                price=price,
                geo=GeoPoint(lat=area.latitude, lon=area.longitude),
            )
        except Exception:
            return None

    def _parse_price(self, text: str) -> Optional[float]:
        import re
        if not text: return None
        text = text.replace(",", "").replace("₹", "").replace("Rs", "").strip()
        m = re.search(r"([\d.]+)\s*(cr|lac|lakh|k)?", text, re.IGNORECASE)
        if not m: return None
        value = float(m.group(1))
        suffix = (m.group(2) or "").lower()
        return value * {"cr": 1e7, "lac": 1e5, "lakh": 1e5, "k": 1e3}.get(suffix, 1)

class NinetyAcresBrowserCrawler:
    def __init__(self, headless: bool = True, slow_mo: int = 0):
        self.headless = headless
        self.slow_mo = slow_mo

    def crawl(self, area: AreaConfig, tx_type: str) -> Generator[PropertyItem, None, None]:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        proxy = {"server": proxy_url} if proxy_url else None
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, slow_mo=self.slow_mo, proxy=proxy)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # Test connectivity
            try:
                page.goto("https://www.google.com", timeout=30000)
                log.info("[Browser-Test] Google title: %s", page.title())
            except Exception as e:
                log.error("[Browser-Test] Failed to reach Google: %s", e)

            category = "rent" if tx_type == "rent" else "sale"
            url = f"https://www.99acres.com/property-for-{category}-in-{area.nintyacres_slug}"
            
            log.info("[99acres-Browser] Starting %s | %s", area.name, tx_type)
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(5)

                debug_path = OUTPUT_DIR / f"debug_99acres_{area.name}_{ts}.png"
                page.screenshot(path=str(debug_path))
                log.info("[99acres-Browser] Saved debug screenshot to %s", debug_path)

                cards = page.query_selector_all("section.projectTuple, div.srpTuple__tupleTable")
                log.info("[99acres-Browser] Found %d cards", len(cards))

                for card in cards:
                    # Basic extraction for now
                    title_el = card.query_selector(".projectTuple__projectName, .srpTuple__propertyName")
                    title = title_el.inner_text() if title_el else "Property in " + area.name
                    
                    price_el = card.query_selector(".projectTuple__price, .srpTuple__price")
                    price_text = price_el.inner_text() if price_el else ""
                    
                    yield PropertyItem(
                        source="99acres",
                        source_id=str(time.time()), # Placeholder
                        url=url,
                        area=area.name,
                        city=area.city,
                        state="Karnataka",
                        title=title.strip(),
                        transaction_type=tx_type,
                        property_type="apartment",
                        price=None, # Simplified
                        geo=GeoPoint(lat=area.latitude, lon=area.longitude),
                    )

            except Exception as exc:
                log.error("[99acres-Browser] Error crawling: %s", exc)
            
            browser.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--area", default="indiranagar")
    parser.add_argument("--tx", choices=["rent", "sale"], default="rent")
    parser.add_argument("--source", choices=["mb", "99"], default="mb")
    parser.add_argument("--headless", action="store_true", default=False)
    parser.add_argument("--slow-mo", type=int, default=0)
    args = parser.parse_args()

    area = TARGET_AREAS.get(args.area.lower())
    if not area:
        print(f"Area {args.area} not found")
        return

    if args.source == "mb":
        crawler = MagicBricksBrowserCrawler(headless=args.headless, slow_mo=args.slow_mo)
    else:
        crawler = NinetyAcresBrowserCrawler(headless=args.headless, slow_mo=args.slow_mo)
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"browser_properties_{ts}.jsonl"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Starting browser-based crawl for %s", area.name)
    count = 0
    with open(output_file, "w") as f:
        for item in crawler.crawl(area, args.tx):
            f.write(json.dumps(item.to_es_doc()) + "\n")
            count += 1
            if count % 5 == 0:
                log.info("Scraped %d items...", count)

    log.info("Crawl complete. Scraped %d items. Saved to %s", count, output_file)

if __name__ == "__main__":
    main()
