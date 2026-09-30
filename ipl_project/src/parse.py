# Stage 2 – parse.py  (coming next)
# JSON → ball-by-ball table and match-level table, cached as parquet.
"""
parse.py - Stage 2: turn raw Cricsheet JSON files into three clean tables.

    balls.csv    one row per delivery   (what happened on every ball)
    matches.csv  one row per match      (teams, venue, toss, result, scores)
    lineups.csv  one row per player per match (who played for whom)

How to run (from the project folder):
    python -m src.parse

The code is split into small functions, each doing one job:

    normalise_team / normalise_venue   fix names
    get_phase                          powerplay / middle / death
    parse_delivery                     one ball  -> one row
    parse_innings                      one innings -> many rows
    parse_match_dict                   one match -> (match row, ball rows, lineup rows)
    parse_all_matches                  every file -> three DataFrames
    save_tables / load_tables          write and read the CSV files
"""
import json
from pathlib import Path

import pandas as pd

from src import config


# ===========================================================================
# 1. Small helper functions
# ===========================================================================
def normalise_team(name: str) -> str:
    """Give renamed franchises one consistent name."""
    return config.TEAM_NAME_MAP.get(name, name)


def normalise_venue(raw_name: str) -> str:
    """'Wankhede Stadium, Mumbai' -> 'Wankhede Stadium' (plus rename fixes)."""
    base_name = raw_name.split(",")[0].strip()
    return config.VENUE_NAME_MAP.get(base_name, base_name)


def get_phase(over_index: int) -> str:
    """Which phase of a T20 innings is this over? (over_index starts at 0)."""
    if over_index <= config.POWERPLAY_LAST_OVER:
        return "powerplay"
    if over_index <= config.MIDDLE_LAST_OVER:
        return "middle"
    return "death"


# ===========================================================================
# 2. One delivery -> one row
# ===========================================================================
def parse_delivery(delivery: dict, context: dict) -> dict:
    """
    Convert one ball from the JSON into a flat dictionary (one table row).

    `context` carries information that is the same for many balls:
    match_id, innings_no, over, delivery_in_over, batting_team,
    bowling_team and name_to_id (player name -> unique ID).

    Cricket rules handled here:
      * WIDE      : not a legal ball, batter did NOT face it.
      * NO-BALL   : not a legal ball, but the batter DID face it.
      * BYES/LEG-BYES : count for the team, but NOT as batter runs and
                        NOT against the bowler.
      * RUN OUT / RETIRED : not a wicket for the bowler.
    """
    name_to_id = context["name_to_id"]
    extras = delivery.get("extras", {})
    wides = extras.get("wides", 0)
    noballs = extras.get("noballs", 0)

    is_wide = wides > 0
    is_noball = noballs > 0
    runs_batter = delivery["runs"]["batter"]

    # --- wicket information (we keep the first wicket if there are two) ---
    wickets = delivery.get("wickets", [])
    wicket = wickets[0] if wickets else None
    wicket_kind = wicket["kind"] if wicket else None
    is_dismissal = wicket is not None and wicket_kind not in config.NOT_A_DISMISSAL_KINDS
    is_bowler_wicket = is_dismissal and wicket_kind in config.BOWLER_WICKET_KINDS
    player_out = wicket["player_out"] if wicket else None

    batter, bowler, non_striker = (
        delivery["batter"], delivery["bowler"], delivery["non_striker"],
    )

    return {
        # -- where in the match --
        "match_id": context["match_id"],
        "innings_no": context["innings_no"],
        "over": context["over"],                      # 0 = first over
        "delivery_in_over": context["delivery_in_over"],  # 1, 2, 3 ... (wides included)
        "phase": get_phase(context["over"]),
        "batting_team": context["batting_team"],
        "bowling_team": context["bowling_team"],
        # -- who --
        "batter": batter,
        "batter_id": name_to_id.get(batter),
        "bowler": bowler,
        "bowler_id": name_to_id.get(bowler),
        "non_striker_id": name_to_id.get(non_striker),
        # -- runs --
        "runs_batter": runs_batter,
        "runs_extras": delivery["runs"]["extras"],
        "runs_total": delivery["runs"]["total"],
        # runs charged to the bowler = bat runs + wides + no-balls
        "runs_bowler": runs_batter + wides + noballs,
        # -- ball type --
        "is_wide": is_wide,
        "is_noball": is_noball,
        "is_legal_ball": not (is_wide or is_noball),   # counts toward the 6 in an over
        "is_ball_faced": not is_wide,                  # counts as a ball faced by the batter
        # -- wicket --
        "is_dismissal": is_dismissal,
        "is_bowler_wicket": is_bowler_wicket,
        "wicket_kind": wicket_kind,
        "player_out": player_out,
        "player_out_id": name_to_id.get(player_out) if player_out else None,
    }


# ===========================================================================
# 3. One innings -> many rows
# ===========================================================================
def parse_innings(innings: dict, innings_no: int, match_id: str,
                  team_names: list, name_to_id: dict) -> list:
    """Walk through every over and delivery of one innings."""
    batting_team = normalise_team(innings["team"])
    # the bowling team is simply "the other team"
    bowling_team = next(t for t in team_names if t != batting_team)

    rows = []
    for over in innings["overs"]:
        for position, delivery in enumerate(over["deliveries"], start=1):
            context = {
                "match_id": match_id,
                "innings_no": innings_no,
                "over": over["over"],
                "delivery_in_over": position,
                "batting_team": batting_team,
                "bowling_team": bowling_team,
                "name_to_id": name_to_id,
            }
            rows.append(parse_delivery(delivery, context))
    return rows


# ===========================================================================
# 4. One match -> match row + ball rows + lineup rows
# ===========================================================================
def _read_outcome(outcome: dict) -> dict:
    """Work out who won and how, including ties and no-results."""
    if outcome.get("result") == "tie":
        result_type = "tie"            # decided by a super over
        winner = outcome.get("eliminator")
    elif outcome.get("winner"):
        result_type = "normal"
        winner = outcome["winner"]
    else:
        result_type = "no_result"
        winner = None
    by = outcome.get("by", {})
    return {
        "winner": normalise_team(winner) if winner else None,
        "result_type": result_type,
        "win_by_runs": by.get("runs"),
        "win_by_wickets": by.get("wickets"),
        "dls_method": outcome.get("method"),   # 'D/L' if rain rules were used
    }


def parse_match_dict(data: dict, match_id: str):
    """
    Turn one loaded JSON file into (match_row, ball_rows, lineup_rows).
    Returns None if the match had no innings at all (abandoned).
    """
    if not data.get("innings"):
        return None

    info = data["info"]
    name_to_id = info.get("registry", {}).get("people", {})
    team_names = [normalise_team(t) for t in info["teams"]]

    # ---- ball table ------------------------------------------------------
    ball_rows = []
    for innings_no, innings in enumerate(data["innings"], start=1):
        if innings.get("super_over"):
            continue  # tie-breaker overs are not part of normal batting stats
        ball_rows += parse_innings(innings, innings_no, match_id, team_names, name_to_id)

    # ---- innings totals (sum of every ball's total runs) -----------------
    def total_for(innings_no: int):
        totals = [r["runs_total"] for r in ball_rows if r["innings_no"] == innings_no]
        return sum(totals) if totals else None

    first_innings = data["innings"][0]
    second_target = None
    if len(data["innings"]) > 1:
        second_target = data["innings"][1].get("target", {}).get("runs")

    # ---- match table -----------------------------------------------------
    date = info["dates"][0]
    event = info.get("event", {})
    toss = info.get("toss", {})
    match_row = {
        "match_id": match_id,
        "date": date,
        "season": int(date[:4]),                       # year of the match
        "match_number": event.get("match_number") or event.get("stage"),
        "venue": normalise_venue(info.get("venue", "Unknown")),
        "city": info.get("city"),
        "team1": team_names[0],
        "team2": team_names[1],
        "toss_winner": normalise_team(toss["winner"]) if toss else None,
        "toss_decision": toss.get("decision"),         # 'bat' or 'field'
        "first_bat_team": normalise_team(first_innings["team"]),
        "first_innings_runs": total_for(1),
        "second_innings_runs": total_for(2),
        "target": second_target,
        "overs_per_side": info.get("overs", 20),       # less than 20 if rain-shortened
        "player_of_match": (info.get("player_of_match") or [None])[0],
        **_read_outcome(info.get("outcome", {})),
    }

    # ---- lineup table (the playing XI of each team) ----------------------
    lineup_rows = []
    for team, players in info.get("players", {}).items():
        for player_name in players:
            lineup_rows.append({
                "match_id": match_id,
                "team": normalise_team(team),
                "player": player_name,
                "player_id": name_to_id.get(player_name),
            })

    return match_row, ball_rows, lineup_rows


# ===========================================================================
# 5. All files -> three tables
# ===========================================================================
def parse_all_matches(raw_dir: Path = config.RAW_DATA_DIR):
    """Read every *.json file in `raw_dir` and build the three tables."""
    match_rows, ball_rows, lineup_rows, skipped = [], [], [], []

    json_files = sorted(Path(raw_dir).glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"No .json files found in {raw_dir}. "
                                "Unzip the Cricsheet IPL download into that folder.")

    for path in json_files:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            parsed = parse_match_dict(data, match_id=path.stem)
        except (json.JSONDecodeError, KeyError) as error:
            skipped.append((path.name, repr(error)))
            continue
        if parsed is None:
            skipped.append((path.name, "no innings (abandoned)"))
            continue
        match_row, balls, lineups = parsed
        match_rows.append(match_row)
        ball_rows += balls
        lineup_rows += lineups

    matches = pd.DataFrame(match_rows)
    matches["date"] = pd.to_datetime(matches["date"])
    matches = matches.sort_values(["date", "match_id"]).reset_index(drop=True)
    balls = pd.DataFrame(ball_rows)
    lineups = pd.DataFrame(lineup_rows)

    if skipped:
        print(f"Skipped {len(skipped)} file(s):")
        for name, reason in skipped:
            print(f"   {name}: {reason}")
    return matches, balls, lineups


# ===========================================================================
# 6. Save, load, summarise
# ===========================================================================
def save_tables(matches, balls, lineups) -> None:
    config.PROCESSED_DIR.mkdir(exist_ok=True)
    matches.to_csv(config.MATCHES_FILE, index=False)
    balls.to_csv(config.BALLS_FILE, index=False)
    lineups.to_csv(config.LINEUPS_FILE, index=False)


def load_tables():
    """Read the saved tables back (fast, no need to re-parse the JSON)."""
    matches = pd.read_csv(config.MATCHES_FILE, parse_dates=["date"])
    balls = pd.read_csv(config.BALLS_FILE)
    lineups = pd.read_csv(config.LINEUPS_FILE)
    return matches, balls, lineups


def print_summary(matches, balls, lineups) -> None:
    """A quick health check so you can see the parse worked."""
    print("\n=== PARSE SUMMARY ===")
    print(f"Matches : {len(matches)}  ({matches.season.min()} to {matches.season.max()})")
    print(f"Balls   : {len(balls):,}")
    print(f"Players : {balls.batter_id.nunique()} unique batters, "
          f"{balls.bowler_id.nunique()} unique bowlers")
    print(f"Balls with a missing player ID: "
          f"{int(balls.batter_id.isna().sum() + balls.bowler_id.isna().sum())}")
    print("\nResult types:")
    print(matches.result_type.value_counts().to_string())
    print("\nMatches per season:")
    print(matches.season.value_counts().sort_index().to_string())
    print("\nTeams:", sorted(set(matches.team1) | set(matches.team2)))
    print("\nTop venues (check for duplicate spellings!):")
    print(matches.venue.value_counts().head(15).to_string())


if __name__ == "__main__":
    matches, balls, lineups = parse_all_matches()
    save_tables(matches, balls, lineups)
    print_summary(matches, balls, lineups)
    print(f"\nSaved tables to: {config.PROCESSED_DIR}")