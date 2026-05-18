"""
MLB Betting Agent — Analysis Layer
===================================
Takes enriched Game objects from data_pipeline and applies the factor
framework: FIP/ERA divergence, park context, pitcher matchup edges,
team form. Produces a structured 'edge report' per game.

IMPORTANT: This layer does NOT place bets. It surfaces analysis for a
human to review. Closing Line Value tracking (clv_tracker.py) is how you
validate whether the analysis is actually any good before risking money.
"""

from dataclasses import dataclass, field


@dataclass
class GameAnalysis:
    matchup: str
    venue: str
    signals: list = field(default_factory=list)   # (label, lean, strength, reasoning)
    pitching_edge: str = "EVEN"
    confidence: str = "LOW"

    def summary(self) -> str:
        lines = [f"\n{self.matchup}  ({self.venue})",
                 f"  Pitching edge: {self.pitching_edge}   |   Confidence: {self.confidence}"]
        if not self.signals:
            lines.append("  No notable signals — likely an efficient line, pass.")
        for label, lean, strength, reason in self.signals:
            lines.append(f"  [{strength}] {label} -> {lean}")
            lines.append(f"        {reason}")
        return "\n".join(lines)


def _fip_era_gap(p):
    """A pitcher whose ERA is far below FIP has been lucky (due to regress worse).
    ERA far above FIP = unlucky (due to regress better). Gap > 0.75 is notable."""
    if p is None or p.era is None or p.fip is None:
        return None
    return round(p.era - p.fip, 2)


def analyze_game(g) -> GameAnalysis:
    """Apply the factor framework to a single enriched game."""
    a = GameAnalysis(matchup=f"{g.away_team} @ {g.home_team}", venue=g.venue)
    ap, hp = g.away_pitcher, g.home_pitcher

    # --- Signal 1: FIP/ERA divergence (regression candidates) ---
    for side, p, team in [("away", ap, g.away_team), ("home", hp, g.home_team)]:
        gap = _fip_era_gap(p)
        if gap is None:
            continue
        if gap <= -0.9:
            a.signals.append((
                f"{p.name} OVERPERFORMING", f"FADE {team} pitching", "MED",
                f"ERA {p.era} but FIP {p.fip} (gap {gap}). Run prevention has "
                f"outpaced underlying skill — expect regression toward FIP."))
        elif gap >= 0.9:
            a.signals.append((
                f"{p.name} UNDERPERFORMING", f"BACK {team} pitching", "MED",
                f"ERA {p.era} but FIP {p.fip} (gap +{gap}). Pitching better than "
                f"ERA shows — line may undervalue this start."))

    # --- Signal 2: Direct pitching matchup (FIP-based) ---
    if ap and hp and ap.fip and hp.fip:
        diff = round(ap.fip - hp.fip, 2)
        if abs(diff) >= 1.0:
            better, team = (("home", g.home_team) if diff > 0 else ("away", g.away_team))
            a.pitching_edge = f"{team} (FIP edge {abs(diff)})"
            strength = "STRONG" if abs(diff) >= 1.75 else "MED"
            a.signals.append((
                "STARTER MISMATCH", f"LEAN {team}", strength,
                f"FIP gap of {abs(diff)} favors {team}'s starter. One of the most "
                f"reliable MLB signals when the gap is real."))

    # --- Signal 3: Coors Field / extreme park ---
    if g.park_factor >= 1.10:
        a.signals.append((
            "EXTREME HITTER PARK", "LEAN OVER (total)", "MED",
            f"{g.venue} park factor {g.park_factor}. Totals play up; pitcher ERAs "
            f"here are noisy. Weight the bat-side and check the wind report."))
    elif g.park_factor <= 0.94:
        a.signals.append((
            "PITCHER PARK", "LEAN UNDER (total)", "WEAK",
            f"{g.venue} park factor {g.park_factor}. Suppresses run scoring."))

    # --- Signal 4: Team form divergence ---
    if g.away_form and g.home_form:
        for f1, f2, team in [(g.away_form, g.home_form, g.away_team),
                             (g.home_form, g.away_form, g.home_team)]:
            if f1.run_diff is not None and f2.run_diff is not None:
                rd_gap = f1.run_diff - f2.run_diff
                if rd_gap >= 60:
                    a.signals.append((
                        "RUN-DIFFERENTIAL EDGE", f"LEAN {team}", "WEAK",
                        f"{team} run differential {f1.run_diff:+d} vs opponent "
                        f"{f2.run_diff:+d}. Underlying quality gap — but check if "
                        f"the market has already priced it."))
                break

    # --- Confidence: based on count + strength of aligned signals ---
    strong = sum(1 for s in a.signals if s[2] == "STRONG")
    med = sum(1 for s in a.signals if s[2] == "MED")
    if strong >= 1 and (strong + med) >= 2:
        a.confidence = "HIGH"
    elif med >= 2 or strong >= 1:
        a.confidence = "MEDIUM"
    else:
        a.confidence = "LOW"
    return a


def analyze_slate(games) -> list[GameAnalysis]:
    return [analyze_game(g) for g in games]
