"""
rendering/cli/run_truth_teller.py
────────────────────────────────
CLI entrypoint to test the multi-agent Bangalore rental verification graph.
"""

from __future__ import annotations

import logging
import os
import sys
import argparse

# Configure root path mapping
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from config.settings import config
from config.logging_utils import setup_logging
from config.constants import SAMPLE_SCENARIOS
from agents.service import TruthTellerService

# Setup CLI logging
setup_logging(log_file=config.CLI_LOG_PATH, console=False)
log = logging.getLogger("CLI")

def display_verdict(final_response: dict):
    """Prints the verdict card to the console."""
    address = final_response.get("address_resolved")
    verdict = final_response.get("final_verdict")

    if not verdict:
        print("\n⚠️ No verdict compiled.")
        return

    print("\n" + "#"*80)
    print("                   🏆 FINAL VERDICT CARD REPORT 🏆                   ")
    print("#"*80)
    print(f" ➡️ Locality: {address.locality if address else 'Bangalore'}")
    print(f" ➡️ Fair Range: Rs.{verdict.fair_range_min:.1f} - Rs.{verdict.fair_range_max:.1f}")
    print(f" ➡️ Overpriced: {verdict.overpriced_percentage}%")
    print(f" ➡️ Upfront Cost: Rs.{verdict.total_upfront_cost:.2f}")
    print(f" ➡️ Access Score: {verdict.neighbourhood_score}/10")
    print(f" ➡️ Red Flags:")
    for flag in verdict.red_flags:
        print(f"     ⚠️ {flag}")
    print(f" ➡️ Smart Questions:")
    for i, q in enumerate(verdict.broker_questionnaire or [], 1):
        print(f"     {i}. {q}")
    print("#"*80)

def run_verification(text: str, label: str):
    print(f"\n🚀 Running verification on: {label}...")
    try:
        result = TruthTellerService.verify_listing(text)
        display_verdict(result)
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rental Truth-Teller CLI")
    parser.add_argument("--listing", type=str, help="Raw listing text")
    parser.add_argument("--file", type=str, help="Path to listing file")
    args = parser.parse_args()

    if args.listing:
        run_verification(args.listing, "CLI INPUT")
    elif args.file:
        with open(args.file, "r") as f:
            run_verification(f.read(), args.file)
    else:
        print("🏠 Welcome to Rental Truth-Teller CLI")
        print("Paste listing text and press Enter twice to analyze. Type 'exit' to quit.")
        while True:
            lines = []
            while True:
                line = input("> " if not lines else "")
                if not line: break
                if line.strip().lower() in ("exit", "quit"): sys.exit(0)
                lines.append(line)
            if lines:
                run_verification("\n".join(lines), "INTERACTIVE INPUT")
