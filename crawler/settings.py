"""
crawler/settings.py
────────────────────
Scrapy project settings for RentalTruth Tier-0 crawler.
"""

import sys
from pathlib import Path

# Make config importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import config

# ── Bot identity ──────────────────────────────────────────────────────────────
BOT_NAME = "rentaltruth"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ── Spiders location ──────────────────────────────────────────────────────────
SPIDER_MODULES = ["crawler.spiders"]
NEWSPIDER_MODULE = "crawler.spiders"

# ── Robots.txt ────────────────────────────────────────────────────────────────
ROBOTSTXT_OBEY = True

# ── Concurrency ───────────────────────────────────────────────────────────────
CONCURRENT_REQUESTS = config.CRAWL_CONCURRENT_REQUESTS
CONCURRENT_REQUESTS_PER_DOMAIN = config.CRAWL_CONCURRENT_REQUESTS_PER_DOMAIN
DOWNLOAD_DELAY = config.CRAWL_DELAY_SECONDS
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0

# ── Retry ─────────────────────────────────────────────────────────────────────
RETRY_ENABLED = True
RETRY_TIMES = config.CRAWL_MAX_RETRIES
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]

# ── Timeouts ──────────────────────────────────────────────────────────────────
DOWNLOAD_TIMEOUT = config.CRAWL_DOWNLOAD_TIMEOUT

# ── Cookies ───────────────────────────────────────────────────────────────────
COOKIES_ENABLED = True
COOKIES_DEBUG = False

# ── HTTP cache (during dev, disable in prod) ──────────────────────────────────
HTTPCACHE_ENABLED = False
HTTPCACHE_EXPIRATION_SECS = 3600
HTTPCACHE_DIR = ".scrapy/httpcache"
HTTPCACHE_IGNORE_HTTP_CODES = [403, 429, 500, 502, 503]

# ── Middlewares ───────────────────────────────────────────────────────────────
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": 90,
    "scrapy.downloadermiddlewares.redirect.RedirectMiddleware": 600,
    "scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware": 810,
}

# ── Item Pipelines ────────────────────────────────────────────────────────────
ITEM_PIPELINES = {
    "crawler.pipelines.elasticsearch_pipeline.ElasticsearchPipeline": 300,
}

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = config.LOG_LEVEL
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# ── Telemetry ─────────────────────────────────────────────────────────────────
TELNETCONSOLE_ENABLED = False

# ── Feed exports (optional CSV/JSON dump for debugging) ───────────────────────
# Uncomment to enable:
# FEEDS = {
#     "output/properties_%(time)s.jsonl": {"format": "jsonlines", "overwrite": True},
# }
