"""
MLB Betting Agent — Data Pipeline
==================================
Pulls tonight's slate, probable pitchers, team form, and pitcher stats
from the free public MLB Stats API (statsapi.mlb.com — no key required).

This is Stage 1 of the build: the data backbone. Odds integration and the
Claude reasoning layer plug into the structured output this produces.
"""

import requests
import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional

MLB_API = "https://statsapi.mlb.com/api/v1"

# Park run-factor lookup (1.00 = neutral). Source: multi-year Statcast park factors.
# Used as a contextual adjustment, not a primary signal.
PARK_FACTORS = {
    "Coors Field": 1.15, "Great American Ball Park": 1.07, "Fenway Park": 1.04,
    "Yankee Stadium": 1.05, "Chase Field": 1.03, "Globe Life Field": 1.01,
    "Citizens Bank Park": 1.04, "Wrigley Field": 1.02, "Dodger Stadium": 0.98,
    "Oracle Park": 0.93, "T-Mobile Park": 0.93, "Petco Park": 0.96,
    "loanDepot park": 0.97, "Tropicana Field": 0.97, "Comerica Park": 0.97,
}


@dataclass
class PitcherStats:
    name: str
    player_id: int
    throws: str = "?"
    era: Optional[float] = None
    whip: Optional[float] = None
    fip: Optional[float] = None          # computed below
    innings: Optional[float] = None
    strikeouts: Optional[int] = None
    walks: Optional[int] = None
    home_runs: Optional[int] = None
    hits: Optional[int] = None
    k_per_9: Optional[float] = None
    bb_per_9: Optional[float] = None
    games_started: Optional[int] = None


@dataclass
class TeamForm:
    name: str
    wins: int = 0
    losses: int = 0
    last_10: str = "?"
    streak: str = "?"
    runs_per_game: Optional[float] = None
    run_diff: Optional[int] = None


@dataclass
class Game:
    game_id: int
    away_team: str
    home_team: str
    venue: str
    game_time: str
    park_factor: float = 1.00
    away_pitcher: Optional[PitcherStats] = None
    home_pitcher: Optional[PitcherStats] = None
    away_form: Optional[TeamForm] = None
    home_form: Optional[TeamForm] = None
    notes: list = field(default_factory=list)


def _get(url: str) -> dict:
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()


def compute_fip(hr, bb, k, ip, constant=3.15):
    """FIP = ((13*HR)+(3*BB)-(2*K))/IP + constant.
    FIP isolates what a pitcher controls — better than ERA for prediction."""
    if not ip or ip == 0:
        return None
    return round(((13 * (hr or 0)) + (3 * (bb or 0)) - (2 * (k or 0))) / ip + constant, 2)


def get_slate(date: str = None) -> list[Game]:
    """Pull all games for a date with probable pitchers and venues."""
    if date is None:
        date = datetime.date.today().isoformat()
    url = f"{MLB_API}/schedule?sportId=1&date={date}&hydrate=probablePitcher,team,venue"
    data = _get(url)
    games = []
    for date_block in data.get("dates", []):
        for g in date_block.get("games", []):
            venue = g.get("venue", {}).get("name", "Unknown")
            game = Game(
                game_id=g["gamePk"],
                away_team=g["teams"]["away"]["team"]["name"],
                home_team=g["teams"]["home"]["team"]["name"],
                venue=venue,
                game_time=g.get("gameDate", "?"),
                park_factor=PARK_FACTORS.get(venue, 1.00),
            )
            ap = g["teams"]["away"].get("probablePitcher")
            hp = g["teams"]["home"].get("probablePitcher")
            if ap:
                game.away_pitcher = PitcherStats(name=ap["fullName"], player_id=ap["id"])
            if hp:
                game.home_pitcher = PitcherStats(name=hp["fullName"], player_id=hp["id"])
            games.append(game)
    return games


def enrich_pitcher(p: PitcherStats, season: int = 2026) -> PitcherStats:
    """Fetch season pitching stats and compute FIP for a probable pitcher."""
    if p is None:
        return None
    url = (f"{MLB_API}/people?personIds={p.player_id}"
           f"&hydrate=stats(group=[pitching],type=[season],season={season})")
    try:
        data = _get(url)
        person = data["people"][0]
        p.throws = person.get("pitchHand", {}).get("code", "?")
        for sgroup in person.get("stats", []):
            for split in sgroup.get("splits", []):
                s = split.get("stat", {})
                p.era = _to_float(s.get("era"))
                p.whip = _to_float(s.get("whip"))
                p.innings = _to_float(s.get("inningsPitched"))
                p.strikeouts = _to_int(s.get("strikeOuts"))
                p.walks = _to_int(s.get("baseOnBalls"))
                p.home_runs = _to_int(s.get("homeRuns"))
                p.hits = _to_int(s.get("hits"))
                p.games_started = _to_int(s.get("gamesStarted"))
                if p.innings:
                    p.k_per_9 = round((p.strikeouts or 0) * 9 / p.innings, 2)
                    p.bb_per_9 = round((p.walks or 0) * 9 / p.innings, 2)
                p.fip = compute_fip(p.home_runs, p.walks, p.strikeouts, p.innings)
    except Exception as e:
        p.throws = p.throws or "?"
    return p


def enrich_team_form(team_name: str, season: int = 2026) -> TeamForm:
    """Fetch standings-based team form: record, last 10, streak, run differential."""
    try:
        data = _get(f"{MLB_API}/standings?leagueId=103,104&season={season}")
        for rec in data.get("records", []):
            for tr in rec.get("teamRecords", []):
                if tr["team"]["name"] == team_name:
                    splits = {s["type"]: s for s in tr.get("records", {}).get("splitRecords", [])}
                    last10 = splits.get("lastTen", {})
                    return TeamForm(
                        name=team_name,
                        wins=tr.get("wins", 0),
                        losses=tr.get("losses", 0),
                        last_10=f"{last10.get('wins','?')}-{last10.get('losses','?')}",
                        streak=tr.get("streak", {}).get("streakCode", "?"),
                        run_diff=tr.get("runDifferential"),
                    )
    except Exception:
        pass
    return TeamForm(name=team_name)


def build_full_slate(date: str = None, season: int = 2026) -> list[Game]:
    """Master function: pull slate and enrich every game with pitcher + team data."""
    games = get_slate(date)
    for g in games:
        g.away_pitcher = enrich_pitcher(g.away_pitcher, season)
        g.home_pitcher = enrich_pitcher(g.home_pitcher, season)
        g.away_form = enrich_team_form(g.away_team, season)
        g.home_form = enrich_team_form(g.home_team, season)
        # Auto-flag contextual notes
        if g.park_factor >= 1.07:
            g.notes.append(f"HITTER-FRIENDLY PARK ({g.venue}, factor {g.park_factor})")
        if g.park_factor <= 0.95:
            g.notes.append(f"PITCHER-FRIENDLY PARK ({g.venue}, factor {g.park_factor})")
    return games


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    slate = build_full_slate()
    print(f"\n{'='*70}\nMLB SLATE — {datetime.date.today().isoformat()}  ({len(slate)} games)\n{'='*70}")
    for g in slate:
        print(f"\n{g.away_team} @ {g.home_team}  —  {g.venue}")
        if g.away_pitcher:
            ap = g.away_pitcher
            print(f"  {ap.name} ({ap.throws}): ERA {ap.era}  FIP {ap.fip}  "
                  f"WHIP {ap.whip}  K/9 {ap.k_per_9}")
        if g.home_pitcher:
            hp = g.home_pitcher
            print(f"  {hp.name} ({hp.throws}): ERA {hp.era}  FIP {hp.fip}  "
                  f"WHIP {hp.whip}  K/9 {hp.k_per_9}")
        for n in g.notes:
            print(f"  >> {n}")
