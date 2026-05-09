#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/run_crawlers.sh
# ────────────────────────
# Orchestrates all Tier-0 property crawlers for Bangalore.
#
# Usage:
#   ./scripts/run_crawlers.sh                  # Run all spiders sequentially
#   ./scripts/run_crawlers.sh magicbricks      # Run a single named spider
#   ./scripts/run_crawlers.sh --parallel       # Run all spiders in parallel
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Resolve project root ─────────────────────────────────────────────────────
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# ── Load .env if present ──────────────────────────────────────────────────────
if [ -f ".env" ]; then
  set -a
  source .env
  set +a
fi

# ── Config ────────────────────────────────────────────────────────────────────
LOG_DIR="${PROJECT_ROOT}/logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
PARALLEL=${PARALLEL:-false}
SPIDERS=("magicbricks" "99acres")
TARGET_SPIDER="${1:-all}"

mkdir -p "$LOG_DIR"

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Pre-flight checks ─────────────────────────────────────────────────────────
log_info "=== RentalTruth Tier-0 Crawler ==="
log_info "Project root : $PROJECT_ROOT"
log_info "Timestamp    : $TIMESTAMP"
log_info "Areas        : ${BANGALORE_AREAS:-Whitefield,Koramangala}"

if ! python -c "import scrapy" 2>/dev/null; then
  log_error "Scrapy not found. Run: pip install -r requirements.txt"
  exit 1
fi

# ── Elasticsearch health check ────────────────────────────────────────────────
ES_HOST="${ES_HOST:-localhost}"
ES_PORT="${ES_PORT:-9200}"
ES_USER="${ES_USERNAME:-elastic}"
ES_PASS="${ES_PASSWORD:-changeme}"

log_info "Checking Elasticsearch at http://$ES_HOST:$ES_PORT …"
if ! curl -sf -u "$ES_USER:$ES_PASS" "http://$ES_HOST:$ES_PORT/_cluster/health" > /dev/null; then
  log_error "Elasticsearch is not reachable. Start it via:"
  log_error "  docker compose -f docker/docker-compose.yml up -d"
  exit 1
fi
log_info "Elasticsearch is up."

# ── Ensure index exists ───────────────────────────────────────────────────────
log_info "Setting up Elasticsearch index…"
python scripts/setup_es_index.py

# ── Run spider function ───────────────────────────────────────────────────────
run_spider() {
  local spider_name="$1"
  local log_file="$LOG_DIR/${spider_name}_${TIMESTAMP}.log"

  log_info "Starting spider: $spider_name → log: $log_file"
  scrapy crawl "$spider_name" \
    --set LOG_FILE="$log_file" \
    --set LOG_LEVEL="${LOG_LEVEL:-INFO}" \
    2>&1 | tee -a "$log_file"

  local exit_code=${PIPESTATUS[0]}
  if [ $exit_code -eq 0 ]; then
    log_info "Spider '$spider_name' completed successfully."
  else
    log_error "Spider '$spider_name' exited with code $exit_code. Check: $log_file"
  fi
  return $exit_code
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
if [[ "$TARGET_SPIDER" == "--parallel" ]]; then
  log_info "Running all spiders in PARALLEL…"
  declare -a PIDS=()
  for spider in "${SPIDERS[@]}"; do
    run_spider "$spider" &
    PIDS+=($!)
  done
  # Wait for all and collect exit codes
  FAILED=0
  for pid in "${PIDS[@]}"; do
    wait "$pid" || FAILED=$((FAILED + 1))
  done
  if [ $FAILED -gt 0 ]; then
    log_error "$FAILED spider(s) failed."
    exit 1
  fi

elif [[ "$TARGET_SPIDER" != "all" ]]; then
  # Run a single named spider
  run_spider "$TARGET_SPIDER"

else
  # Sequential (default)
  log_info "Running all spiders SEQUENTIALLY…"
  FAILED=0
  for spider in "${SPIDERS[@]}"; do
    run_spider "$spider" || FAILED=$((FAILED + 1))
  done
  if [ $FAILED -gt 0 ]; then
    log_error "$FAILED spider(s) failed."
    exit 1
  fi
fi

log_info "=== All crawls complete. Logs saved to $LOG_DIR ==="
