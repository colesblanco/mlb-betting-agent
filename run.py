"""
MLB Betting Agent — Main Runner
=================================
Ties the pipeline + analysis together into a daily slate report.

  python run.py            -> analyze today's slate
  python run.py 2026-05-19 -> analyze a specific date

This is the Stage 1-3 build: live data + factor analysis. Next stages
(odds integration, Claude reasoning layer, sentiment scan) plug in where
marked TODO below.

Reminder: this surfaces analysis for YOU to review and place manually.
It is a research tool, not an autobetting system.
"""

import sys
import datetime
from data_pipeline import build_full_slate
from analysis import analyze_slate


def run(date: str = None):
    date = date or datetime.date.today().isoformat()
    print(f"\n{'#'*70}")
    print(f"#  MLB BETTING AGENT — SLATE ANALYSIS — {date}")
    print(f"{'#'*70}")
    print("Pulling live data from MLB Stats API...")

    games = build_full_slate(date)
    if not games:
        print("No games found for this date.")
        return

    analyses = analyze_slate(games)

    # --- TODO Stage 2: pull live odds here and attach to each game ---
    #   from odds import attach_odds; attach_odds(games)
    # --- TODO Stage 4: sentiment scan for late scratches / news ---
    #   from sentiment import scan_news; scan_news(games)

    # Sort so highest-confidence games surface first
    rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    analyses.sort(key=lambda a: rank.get(a.confidence, 3))

    high = [a for a in analyses if a.confidence == "HIGH"]
    med = [a for a in analyses if a.confidence == "MEDIUM"]

    print(f"\nAnalyzed {len(games)} games. "
          f"{len(high)} high-confidence, {len(med)} medium-confidence.\n")

    print(f"{'='*70}\nTOP OPPORTUNITIES\n{'='*70}")
    shown = high + med
    if not shown:
        print("\nNo high- or medium-confidence edges tonight. "
              "Efficient slate — discipline means passing.")
    for a in shown:
        print(a.summary())

    print(f"\n{'='*70}\nFULL SLATE (all games)\n{'='*70}")
    for a in analyses:
        print(a.summary())

    print(f"\n{'='*70}")
    print("NEXT STEP: For any pick you like, log it with the line you'd get:")
    print("  python clv_tracker.py log")
    print("Then track CLV. Do not bet real money until CLV is positive over ~100 picks.")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else None)
