#!/usr/bin/env python3
"""
NaukriGulf automation script for GitHub Actions self-hosted runner.
This script runs the NaukriGulf apply process with proper logging.
"""

from src.naukrigulf_apply import run_naukrigulf_apply

def main():
    """Main execution function."""
    print("Starting NaukriGulf automation on self-hosted runner...")
    
    # Run NaukriGulf automation
    results = run_naukrigulf_apply(max_applies=2)
    
    # Print results
    applied_count = sum(1 for r in results if r.status == "success")
    print(f"Applied: {applied_count} jobs")
    print(f"Total results: {len(results)}")
    
    for r in results:
        print(f"  {r.status}: {r.title} at {r.company}")

if __name__ == "__main__":
    main()
