"""
scripts/run_indeed_apply.py
CLI entry point for Indeed Easy Apply.

Usage:
    python scripts/run_indeed_apply.py --dry-run      # scan + report, no submits
    python scripts/run_indeed_apply.py                # live apply (INDEED_ENABLED=true required)
    python scripts/run_indeed_apply.py --max 5        # apply up to 5 jobs
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from src.indeed_apply import run_indeed_apply

parser = argparse.ArgumentParser(description="Indeed Easy Apply runner")
parser.add_argument("--dry-run", action="store_true", help="Scan only, no applications")
parser.add_argument("--max", type=int, default=3, help="Max applications per run")
args = parser.parse_args()

results = run_indeed_apply(dry_run=args.dry_run, max_applies=args.max)

if not args.dry_run:
    print()
    for r in results:
        print(f"{r.status.value:<20} | {r.title[:55]:<55} | {r.company[:30]}")
    print(f"\nTotal: {len(results)} | Applied: {sum(1 for r in results if r.status.value == 'success')}")
