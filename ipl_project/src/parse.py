"""
parse.py
========
Converts raw Cricsheet JSON match dicts into three tidy tables:

    match_row  – dict  – one row for matches.parquet
    balls      – list[dict] – one row per delivery for balls.parquet
    lineups    – list[dict] – one row per player per match for lineups.parquet

Public API
----------
    parse_match_dict(data, match_id) -> tuple | None
    parse_all(data_dir, ...)         -> (matches_df, balls_df, lineups_df)

If a match has no innings (abandoned before a ball was bowled) the function
returns None and the caller should skip it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import (
    BALL_TABLE_PATH,
    BOWLER_WICKET_KINDS,
    DATA_DIR,
    DEATH_OVERS,
    MATCH_TABLE_PATH,
    MIDDLE_OVERS,
    NOT_A_DISMISSAL_KINDS,
    POWERPLAY_OVERS,
    TEAM_NAME_MAP,
    VENUE_NAME_MAP,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants local to the parser
# ---------------------------------------------------------------------------
# Extras that are NOT charged to the bowler (byes & leg-byes)
_BYES_KINDS = {"byes", "legbyes"}

# Extras that make the delivery a no-ball (batter faces it, not a legal ball)
_NOBALL_KINDS = {"noballs"}

# Extras that make the delivery a wide (batter does NOT face it, not legal)
_WIDE_KINDS = {"wides"}


# ---------------------------------------------------------------------------
# Name-normalisation helpers
# ---------------------------------------------------------------------------

def _norm_team(name: str) -> str:
    """Return the canonical franchise name, or the name unchanged if unknown."""
    return TEAM_NAME_MAP.get(name, name)


def _norm_venue(raw: str) -> str:
    """
    Strip everything after the first comma, then look up in VENUE_NAME_MAP.
    If not found, return the stripped name as-is (so new venues are still usable).
    """
    short = raw.split(",")[0].strip()
    return VENUE_NAME_MAP.get(raw, VENUE_NAME_MAP.get(short, short))


# ---------------------------------------------------------------------------
# Phase helper
# ---------------------------------------------------------------------------

def _phase(over_index: int) -> str:
    if over_index in POWERPLAY_OVERS:
        return "powerplay"
    if over_index in MIDDLE_OVERS:
        return "middle"
    return "death"


# ---------------------------------------------------------------------------
# Delivery parser
# ---------------------------------------------------------------------------

def _parse_delivery(
    delivery: dict,
    *,
    match_id: str,
    innings_no: int,
    batting_team: str,
    bowling_team: str,
    over_index: int,
    delivery_in_over: int,
    registry: dict[str, str],
) -> dict:
    """
    Turn one Cricsheet delivery dict into a flat row dict.

    Cricket rules implemented here
    --------------------------------
    1. Wides  -> not a legal ball, batter does NOT face it.
    2. No-balls -> not a legal ball, but batter DOES face it.
    3. Byes / leg-byes -> not charged to the batter OR the bowler.
    4. Bowler wickets: only bowled / caught / c&b / lbw / stumped / hit wicket.
    5. "retired hurt" / "retired not out" are NOT dismissals.
    """
    extras: dict[str, int] = delivery.get("extras", {})
    runs_info: dict = delivery["runs"]

    batter = delivery["batter"]
    bowler = delivery["bowler"]

    # -- Is it a wide? --
    is_wide = bool(extras.get("wides", 0))

    # -- Is it a no-ball? --
    is_noball = bool(extras.get("noballs", 0))

    # -- Legal ball / ball faced --
    is_legal_ball = not (is_wide or is_noball)
    is_ball_faced = not is_wide  # wide: batter didn't face; no-ball: they did

    # -- Runs --
    runs_batter: int = runs_info["batter"]

    # Extras breakdown
    runs_wides    = extras.get("wides", 0)
    runs_noballs  = extras.get("noballs", 0)
    runs_byes     = extras.get("byes", 0)
    runs_legbyes  = extras.get("legbyes", 0)
    runs_penalty  = extras.get("penalty", 0)

    # Runs attributed to the bowler:
    #   batter runs + wide penalty + noball penalty
    #   but NOT byes or leg-byes (those are fielding errors)
    runs_bowler = runs_batter + runs_wides + runs_noballs

    runs_total: int = runs_info["total"]

    # -- Wicket handling --
    raw_wickets: list[dict] = delivery.get("wickets", [])
    # A ball can have >1 entry (e.g. run-out + the actual wicket) but we only
    # care about the first real dismissal for the batting side.
    dismissal_kind = None
    player_out = None
    for w in raw_wickets:
        kind = w.get("kind", "")
        if kind not in NOT_A_DISMISSAL_KINDS:
            dismissal_kind = kind
            player_out = w.get("player_out")
            break

    is_dismissal = dismissal_kind is not None
    is_bowler_wicket = dismissal_kind in BOWLER_WICKET_KINDS if is_dismissal else False

    player_out_id = registry.get(player_out) if player_out else None

    return {
        "match_id":          match_id,
        "innings_no":        innings_no,
        "batting_team":      batting_team,
        "bowling_team":      bowling_team,
        "over":              over_index,
        "delivery_in_over":  delivery_in_over,
        "phase":             _phase(over_index),
        "batter":            batter,
        "batter_id":         registry.get(batter),
        "bowler":            bowler,
        "bowler_id":         registry.get(bowler),
        "non_striker":       delivery.get("non_striker"),
        "runs_batter":       runs_batter,
        "runs_bowler":       runs_bowler,
        "runs_extras":       runs_total - runs_batter,
        "runs_total":        runs_total,
        "runs_wides":        runs_wides,
        "runs_noballs":      runs_noballs,
        "runs_byes":         runs_byes,
        "runs_legbyes":      runs_legbyes,
        "runs_penalty":      runs_penalty,
        "is_wide":           is_wide,
        "is_noball":         is_noball,
        "is_legal_ball":     is_legal_ball,
        "is_ball_faced":     is_ball_faced,
        "is_dismissal":      is_dismissal,
        "is_bowler_wicket":  is_bowler_wicket,
        "dismissal_kind":    dismissal_kind,
        "player_out":        player_out,
        "player_out_id":     player_out_id,
    }


# ---------------------------------------------------------------------------
# Innings parser
# ---------------------------------------------------------------------------

def _parse_innings(
    innings_data: dict,
    *,
    match_id: str,
    innings_no: int,
    opposing_team: str,
    registry: dict[str, str],
) -> list[dict]:
    """Parse all deliveries in one innings into a list of row dicts."""
    batting_team = _norm_team(innings_data.get("team", ""))
    bowling_team = _norm_team(opposing_team)

    rows: list[dict] = []
    for over_data in innings_data.get("overs", []):
        over_index: int = over_data["over"]
        delivery_counter = 0

        for delivery in over_data.get("deliveries", []):
            delivery_counter += 1

            row = _parse_delivery(
                delivery,
                match_id=match_id,
                innings_no=innings_no,
                batting_team=batting_team,
                bowling_team=bowling_team,
                over_index=over_index,
                delivery_in_over=delivery_counter,
                registry=registry,
            )
            rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Match-level parser
# ---------------------------------------------------------------------------

def parse_match_dict(
    data: dict[str, Any],
    match_id: str,
) -> tuple[dict, list[dict], list[dict]] | None:
    """
    Parse one Cricsheet match dict.

    Returns
    -------
    (match_row, balls, lineups)  or  None if the match had no innings.

    match_row : dict
        Flat dict suitable for a matches table.
    balls : list[dict]
        One dict per delivery (super overs excluded).
    lineups : list[dict]
        One dict per player per team in this match.
    """
    info: dict = data.get("info", {})
    innings_list: list[dict] = data.get("innings", [])

    # Skip matches that never started
    if not innings_list:
        return None

    # Also skip if the only innings is a super over
    playable = [i for i in innings_list if not i.get("super_over")]
    if not playable:
        return None

    registry: dict[str, str] = info.get("registry", {}).get("people", {})

    # -- Teams --
    raw_teams: list[str] = info.get("teams", [])
    team1 = _norm_team(raw_teams[0]) if len(raw_teams) > 0 else ""
    team2 = _norm_team(raw_teams[1]) if len(raw_teams) > 1 else ""

    # -- Venue --
    venue = _norm_venue(info.get("venue", ""))

    # -- Date / season --
    dates = info.get("dates", [])
    date_str = dates[0] if dates else ""
    season = int(date_str[:4]) if date_str else None

    # -- Toss --
    toss = info.get("toss", {})
    toss_winner   = _norm_team(toss.get("winner", ""))
    toss_decision = toss.get("decision", "")

    # -- Outcome --
    outcome: dict = info.get("outcome", {})
    raw_winner = outcome.get("winner", "")
    winner = _norm_team(raw_winner) if raw_winner else None

    by: dict = outcome.get("by", {})
    win_by_runs    = by.get("runs")
    win_by_wickets = by.get("wickets")

    result_text = outcome.get("result", "")
    if result_text == "no result":
        result_type = "no_result"
        winner = None
    elif result_text == "tie":
        result_type = "tie"
        # In a tie decided by eliminator/super over, outcome may still name a winner
        winner = _norm_team(outcome.get("eliminator", "")) or winner
    elif winner:
        result_type = "winner"
    else:
        result_type = "unknown"

    # -- Parse each innings (skip super overs) --
    all_balls: list[dict] = []
    innings_runs: list[int] = []
    target: int | None = None

    for idx, inn in enumerate(innings_list, start=1):
        if inn.get("super_over"):
            continue  # exclude super-over deliveries from stats

        # Determine the opposing team (the other team from the two teams list)
        batting_team_raw = inn.get("team", "")
        if batting_team_raw == raw_teams[0]:
            opposing = raw_teams[1] if len(raw_teams) > 1 else ""
        else:
            opposing = raw_teams[0]

        balls = _parse_innings(
            inn,
            match_id=match_id,
            innings_no=idx,
            opposing_team=opposing,
            registry=registry,
        )
        all_balls.extend(balls)
        innings_runs.append(sum(b["runs_total"] for b in balls))

        # Target is recorded in the second innings
        if "target" in inn:
            target = inn["target"].get("runs")

    first_innings_runs  = innings_runs[0] if len(innings_runs) > 0 else None
    second_innings_runs = innings_runs[1] if len(innings_runs) > 1 else None

    # -- Lineups --
    lineups: list[dict] = []
    players_map: dict[str, list[str]] = info.get("players", {})
    for team_raw, player_names in players_map.items():
        team_norm = _norm_team(team_raw)
        for name in player_names:
            lineups.append({
                "match_id":  match_id,
                "team":      team_norm,
                "player":    name,
                "player_id": registry.get(name),
            })

    # -- Match row --
    match_row = {
        "match_id":            match_id,
        "date":                date_str,
        "season":              season,
        "venue":               venue,
        "team1":               team1,
        "team2":               team2,
        "toss_winner":         toss_winner,
        "toss_decision":       toss_decision,
        "winner":              winner,
        "win_by_runs":         win_by_runs,
        "win_by_wickets":      win_by_wickets,
        "result_type":         result_type,
        "first_innings_runs":  first_innings_runs,
        "second_innings_runs": second_innings_runs,
        "target":              target,
    }

    return match_row, all_balls, lineups


# ---------------------------------------------------------------------------
# Batch parser: process the whole data directory
# ---------------------------------------------------------------------------

def parse_all(
    data_dir: Path | None = None,
    save: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Walk *data_dir* (default: DATA_DIR from config), parse every *.json file,
    and return three DataFrames.  Optionally saves them as parquet files.
    """
    data_dir = data_dir or DATA_DIR

    match_rows:  list[dict] = []
    ball_rows:   list[dict] = []
    lineup_rows: list[dict] = []

    json_files = sorted(data_dir.glob("*.json"))
    if not json_files:
        log.warning("No JSON files found in %s", data_dir)

    skipped = 0
    for path in json_files:
        match_id = path.stem
        try:
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            log.error("Could not read %s: %s", path, exc)
            continue

        result = parse_match_dict(data, match_id)
        if result is None:
            skipped += 1
            continue

        match_row, balls, lineups = result
        match_rows.append(match_row)
        ball_rows.extend(balls)
        lineup_rows.extend(lineups)

    matches_df = pd.DataFrame(match_rows)
    balls_df   = pd.DataFrame(ball_rows)
    lineups_df = pd.DataFrame(lineup_rows)

    # -- Summary --
    print(f"\n{'='*60}")
    print(f"Matches parsed  : {len(matches_df):>6}")
    print(f"Matches skipped : {skipped:>6}  (no innings)")
    print(f"Deliveries      : {len(balls_df):>6}")
    print(f"Lineup entries  : {len(lineups_df):>6}")
    if len(matches_df):
        print("\nTeams:")
        teams = pd.concat([matches_df["team1"], matches_df["team2"]]).value_counts()
        for t, c in teams.items():
            print(f"  {t:<45} {c:>4}")
        print("\nVenues (top 15):")
        for v, c in matches_df["venue"].value_counts().head(15).items():
            print(f"  {v:<50} {c:>4}")
        missing_ids = balls_df["batter_id"].isna().sum() + balls_df["bowler_id"].isna().sum()
        print(f"\nMissing player IDs in balls table: {missing_ids}")
    print("="*60)

    if save:
        BALL_TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
        balls_df.to_parquet(BALL_TABLE_PATH, index=False)
        matches_df.to_parquet(MATCH_TABLE_PATH, index=False)
        print(f"Saved -> {BALL_TABLE_PATH}")
        print(f"Saved -> {MATCH_TABLE_PATH}")

    return matches_df, balls_df, lineups_df


# ---------------------------------------------------------------------------
# Entry point: python -m src.parse
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parse_all()
