"""
inspect_one.py  (Stage 1 learning script)
==========================================
Encoding fix: we force stdout to UTF-8 so Rich works on Windows.
Opens one Cricsheet JSON file and prints every important section
in a clear, readable format so you can see exactly what the data looks like.

Run from the project root:
    python src/inspect_one.py
Or pick a specific file:
    python src/inspect_one.py 1304047
"""

import json
import io
import os
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
import sys
# Re-open stdout as UTF-8 on Windows so Rich can render box-drawing chars
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path

# ── Allow importing config from the same src/ folder ─────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
import config

# ── Rich for colourful terminal output ───────────────────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
    RICH = True
except ImportError:
    RICH = False

console = Console() if RICH else None

def _print(msg: str, style: str = "") -> None:
    if RICH:
        console.print(msg, style=style)
    else:
        print(msg)

def _rule(title: str) -> None:
    if RICH:
        console.rule(f"[bold cyan]{title}[/]")
    else:
        print(f"\n{'─'*60}\n  {title}\n{'─'*60}")


# ─────────────────────────────────────────────────────────────────────────────
def inspect(json_path: Path) -> None:
    """
    Load one Cricsheet IPL JSON file and pretty-print:
      1. Match metadata (teams, date, venue, toss, result)
      2. The player registry (name → unique ID)
      3. The first 12 deliveries of each innings
      4. A summary of quirks (wides, no-balls, extras, wickets)
    """
    with open(json_path, encoding="utf-8") as fh:
        raw = json.load(fh)

    info    = raw["info"]
    innings = raw["innings"]

    # ── 1. Match metadata ─────────────────────────────────────────────────────
    _rule("1. MATCH METADATA")

    date    = info["dates"][0]
    season  = info.get("season", "?")
    venue   = info.get("venue", "?")
    city    = info.get("city", "?")
    teams   = info["teams"]
    toss_w  = info["toss"]["winner"]
    toss_d  = info["toss"]["decision"]
    outcome = info.get("outcome", {})

    if RICH:
        meta_table = Table(box=box.SIMPLE_HEAVY, show_header=False)
        meta_table.add_column("Key",   style="bold yellow", width=18)
        meta_table.add_column("Value", style="white")
        rows = [
            ("Match file",   json_path.name),
            ("Date",         date),
            ("Season",       season),
            ("Venue",        venue),
            ("City",         city),
            ("Team A",       teams[0]),
            ("Team B",       teams[1]),
            ("Toss winner",  f"{toss_w} -> chose to {toss_d}"),
            ("Result",       _outcome_str(outcome)),
        ]
        for k, v in rows:
            meta_table.add_row(k, v)
        console.print(meta_table)
    else:
        print(f"  File    : {json_path.name}")
        print(f"  Date    : {date}  Season: {season}")
        print(f"  Venue   : {venue}, {city}")
        print(f"  Teams   : {teams[0]}  vs  {teams[1]}")
        print(f"  Toss    : {toss_w} chose to {toss_d}")
        print(f"  Result  : {_outcome_str(outcome)}")

    # ── 2. Player registry ────────────────────────────────────────────────────
    _rule("2. PLAYER REGISTRY  (name → unique Cricsheet ID)")
    registry = info["registry"]["people"]
    _print(
        f"  [bold]{len(registry)} players registered in this match[/]"
        if RICH else f"  {len(registry)} players registered in this match"
    )
    _print("  Why IDs matter: 'SC Ganguly' and 'Sourav Ganguly' would be the SAME player.\n"
           "  The ID ensures we never confuse or double-count anyone.", "dim")

    if RICH:
        reg_table = Table("Name", "Cricsheet ID", box=box.MINIMAL_DOUBLE_HEAD)
        for name, pid in sorted(registry.items()):
            reg_table.add_row(name, f"[green]{pid}[/]")
        console.print(reg_table)
    else:
        for name, pid in sorted(registry.items()):
            print(f"  {name:<30} {pid}")

    # ── 3. First deliveries of each innings ───────────────────────────────────
    _rule("3. FIRST 12 DELIVERIES OF EACH INNINGS")
    _print(
        "  Each delivery is one row. Key fields explained below.\n"
        "  • [yellow]actual_delivery[/]: 0.3 means over 0, 3rd legal delivery\n"
        "  • A WIDE has the same actual_delivery as the next ball (repeated number)\n"
        "  • [yellow]batter runs[/] = runs scored by the bat (not extras)\n"
        "  • [yellow]extras[/] = wides, no-balls, byes, leg-byes\n"
        "  • [yellow]wicket[/] = who got out, how, and bowler's wicket (or run-out)"
        if RICH else
        "  Key: actual_delivery | batter | bowler | bat_runs | extras_type | wicket"
    )

    for inn_idx, inn in enumerate(innings):
        team = inn["team"]
        _print(f"\n  [bold magenta]Innings {inn_idx+1}: {team}[/]" if RICH
               else f"\n  Innings {inn_idx+1}: {team}")

        deliveries_shown = 0
        for over_block in inn["overs"]:
            ov = over_block["over"]
            for d in over_block["deliveries"]:
                if deliveries_shown >= 12:
                    break

                ad          = d.get("actual_delivery", "?")
                batter      = d["batter"]
                bowler      = d["bowler"]
                bat_runs    = d["runs"]["batter"]
                total_runs  = d["runs"]["total"]
                extras      = d.get("extras", {})
                extras_str  = ", ".join(f"{k}={v}" for k, v in extras.items()) or "—"
                wickets     = d.get("wickets", [])
                wicket_str  = _wicket_str(wickets) if wickets else "—"

                if RICH:
                    console.print(
                        f"    {str(ad):<6} "
                        f"[cyan]{batter:<22}[/] "
                        f"[yellow]bat={bat_runs}[/]  "
                        f"tot={total_runs}  "
                        f"extras=[dim]{extras_str}[/]  "
                        f"wicket=[red]{wicket_str}[/]"
                    )
                else:
                    print(
                        f"    {ad:<6}  {batter:<22}  "
                        f"bat={bat_runs}  tot={total_runs}  "
                        f"extras={extras_str}  out={wicket_str}"
                    )
                deliveries_shown += 1
            if deliveries_shown >= 12:
                break

    # ── 4. Quirk summary ──────────────────────────────────────────────────────
    _rule("4. QUIRK SUMMARY FOR THIS MATCH")
    for inn_idx, inn in enumerate(innings):
        team = inn["team"]
        counts = _count_quirks(inn)
        _print(
            f"  [bold]{team}[/]  "
            f"wides={counts['wides']}  "
            f"no-balls={counts['noballs']}  "
            f"byes={counts['byes']}  "
            f"leg-byes={counts['legbyes']}  "
            f"wickets={counts['wickets']}  "
            f"run-outs={counts['runouts']}  "
            f"total_balls_faced={counts['legal_balls']}"
            if RICH else
            f"  {team}: wides={counts['wides']}  no-balls={counts['noballs']}  "
            f"byes={counts['byes']}  legbyes={counts['legbyes']}  "
            f"wickets={counts['wickets']}  runouts={counts['runouts']}  "
            f"legal_balls={counts['legal_balls']}"
        )

    _rule("DONE — Stage 1 inspection complete ✓")


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def _outcome_str(outcome: dict) -> str:
    """Turn the outcome dict into a readable sentence."""
    if not outcome:
        return "No result"
    winner = outcome.get("winner", "?")
    by     = outcome.get("by", {})
    if "runs" in by:
        return f"{winner} won by {by['runs']} runs"
    if "wickets" in by:
        return f"{winner} won by {by['wickets']} wickets"
    if outcome.get("result") == "tie":
        return "Tie"
    return str(outcome)


def _wicket_str(wickets: list) -> str:
    """Summarise a wickets list into a short string."""
    parts = []
    for w in wickets:
        kind       = w.get("kind", "?")
        player_out = w.get("player_out", "?")
        parts.append(f"{player_out} ({kind})")
    return " | ".join(parts)


def _count_quirks(innings_block: dict) -> dict:
    """Count wides, no-balls, byes, leg-byes, wickets, run-outs, legal balls."""
    c = dict(wides=0, noballs=0, byes=0, legbyes=0,
             wickets=0, runouts=0, legal_balls=0)
    for ov in innings_block["overs"]:
        for d in ov["deliveries"]:
            extras = d.get("extras", {})
            if "wides" in extras:
                c["wides"] += 1
                # wides do NOT count as a ball faced by the batter
            elif "noballs" in extras:
                c["noballs"] += 1
                c["legal_balls"] += 1   # no-ball still counts as a ball faced
            else:
                c["legal_balls"] += 1

            if "byes"    in extras: c["byes"]    += 1
            if "legbyes" in extras: c["legbyes"] += 1

            for w in d.get("wickets", []):
                c["wickets"] += 1
                if w.get("kind") == "run out":
                    c["runouts"] += 1
    return c


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1:
        # User passed a match ID like:  python src/inspect_one.py 1304047
        match_id = sys.argv[1].strip()
        path = config.DATA_DIR / f"{match_id}.json"
    else:
        # Default: grab the first JSON in the data folder
        files = sorted(config.DATA_DIR.glob("*.json"))
        if not files:
            raise FileNotFoundError(f"No JSON files found in {config.DATA_DIR}")
        path = files[0]

    if not path.exists():
        raise FileNotFoundError(f"Match file not found: {path}")

    inspect(path)
