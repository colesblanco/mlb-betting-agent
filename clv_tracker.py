"""
MLB Betting Agent — Closing Line Value Tracker
================================================
The most important file in this project. Per the research: beating the
closing line by ~X% projects to ~X% long-run ROI. Before risking real
money, the agent must demonstrate POSITIVE CLV across 100+ logged picks.

This logs every recommendation with the line at analysis time. After each
game's line closes, you record the closing line and the tool computes CLV.

Usage:
  python clv_tracker.py log     -> record a new pick (interactive)
  python clv_tracker.py close   -> enter closing lines for open picks
  python clv_tracker.py report  -> CLV summary so far
"""

import json
import os
import sys
import datetime

LOG_FILE = os.path.join(os.path.dirname(__file__), "clv_log.json")


def _load():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE) as f:
        return json.load(f)


def _save(rows):
    with open(LOG_FILE, "w") as f:
        json.dump(rows, f, indent=2)


def american_to_prob(odds: int) -> float:
    """Convert American odds to implied probability."""
    if odds < 0:
        return -odds / (-odds + 100)
    return 100 / (odds + 100)


def log_pick():
    rows = _load()
    print("\n--- Log a new pick ---")
    matchup = input("Matchup (e.g. Dodgers @ Padres): ").strip()
    pick = input("Your pick (team / over / under): ").strip()
    bet_line = int(input("Line you got (American odds, e.g. -120): ").strip())
    confidence = input("Agent confidence (LOW/MEDIUM/HIGH): ").strip().upper()
    rows.append({
        "date": datetime.date.today().isoformat(),
        "matchup": matchup,
        "pick": pick,
        "bet_line": bet_line,
        "closing_line": None,
        "confidence": confidence,
        "result": None,
    })
    _save(rows)
    print(f"Logged. {len(rows)} total picks tracked.")


def close_picks():
    rows = _load()
    open_rows = [r for r in rows if r["closing_line"] is None]
    if not open_rows:
        print("No open picks to close.")
        return
    for r in open_rows:
        print(f"\n{r['date']}  {r['matchup']}  —  {r['pick']} @ {r['bet_line']}")
        cl = input("  Closing line (American, blank to skip): ").strip()
        if cl:
            r["closing_line"] = int(cl)
    _save(rows)
    print("Closing lines updated.")


def report():
    rows = _load()
    closed = [r for r in rows if r["closing_line"] is not None]
    if not closed:
        print("\nNo closed picks yet. Log picks and enter closing lines first.")
        return
    total_clv = 0.0
    beats = 0
    print(f"\n{'='*64}\nCLV REPORT  —  {len(closed)} closed picks\n{'='*64}")
    for r in closed:
        bet_prob = american_to_prob(r["bet_line"])
        close_prob = american_to_prob(r["closing_line"])
        # Positive CLV = you got a better (lower implied prob) price than close
        clv = (close_prob - bet_prob) * 100
        total_clv += clv
        if clv > 0:
            beats += 1
        flag = "BEAT" if clv > 0 else "lost"
        print(f"  {r['matchup'][:34]:34} {r['pick'][:12]:12} "
              f"bet {r['bet_line']:+5d} / close {r['closing_line']:+5d}  "
              f"CLV {clv:+.2f}%  [{flag}]")
    avg = total_clv / len(closed)
    print(f"{'-'*64}")
    print(f"  Average CLV: {avg:+.2f}%   |   Beat close: {beats}/{len(closed)} "
          f"({beats/len(closed)*100:.0f}%)")
    print(f"{'='*64}")
    if len(closed) < 100:
        print(f"  NOTE: {len(closed)}/100 picks. Need ~100+ before trusting this.")
    elif avg > 0:
        print("  Positive CLV over a real sample — the analysis has signal.")
    else:
        print("  Negative CLV — the model is not beating the market. Do not bet real money.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"log": log_pick, "close": close_picks, "report": report}.get(cmd, report)()
