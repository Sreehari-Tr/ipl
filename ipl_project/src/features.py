"""
features.py  –  Stage 3
========================
Turns the ball-by-ball table into ready-to-use player statistics.

Two kinds of stats are produced
--------------------------------
1. RAW stats   – the plain counts/averages from historical data.
2. SHRUNK stats – pulled toward the league average when a player has few
                  balls (Bayesian / James-Stein shrinkage).
                  Formula:  shrunk = (n * personal + k * league_avg) / (n + k)
                  where n = balls faced/bowled and k = SHRINKAGE_K_* from config.

Stats are split by PHASE (powerplay / middle / death) so the model can see
that a batter might be great in the powerplay but weak at the death.

Public API
----------
    build_batter_features(balls_df, up_to_match_id=None) -> pd.DataFrame
    build_bowler_features(balls_df, up_to_match_id=None) -> pd.DataFrame
    build_all_features(balls_df, matches_df)             -> (bat_df, bowl_df)
    load_features()                                       -> (bat_df, bowl_df)

    run python -m src.features  to build and save feature files.

Output files (in cache/)
-------------------------
    batter_features.parquet   – one row per (batter_id, phase)
    bowler_features.parquet   – one row per (bowler_id, phase)
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import numpy as np

from src.config import (
    BALL_TABLE_PATH,
    MATCH_TABLE_PATH,
    CACHE_DIR,
    SHRINKAGE_K_BAT,
    SHRINKAGE_K_BOWL,
)

log = logging.getLogger(__name__)

# Output paths
BATTER_FEATURES_PATH = CACHE_DIR / "batter_features.parquet"
BOWLER_FEATURES_PATH = CACHE_DIR / "bowler_features.parquet"

PHASES = ["powerplay", "middle", "death"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _shrink(personal: pd.Series, n: pd.Series, league_avg: float, k: float) -> pd.Series:
    """
    Apply Bayesian shrinkage toward the league average.

        shrunk = (n * personal + k * league_avg) / (n + k)

    When n is small the result leans toward league_avg.
    When n >> k the result is almost equal to personal.
    """
    return (n * personal + k * league_avg) / (n + k)


def _boundary_rate(fours: pd.Series, sixes: pd.Series, balls: pd.Series) -> pd.Series:
    """Fraction of legal balls that went for a boundary (4 or 6)."""
    return (fours + sixes) / balls.replace(0, np.nan)


# ---------------------------------------------------------------------------
# Batter features
# ---------------------------------------------------------------------------

def build_batter_features(balls_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute batting statistics grouped by (batter_id, phase).

    Columns produced
    ----------------
    batter_id, phase,
    balls_faced, runs, dismissals,
    strike_rate_raw,   strike_rate_shrunk,
    avg_raw,           avg_shrunk,
    boundary_rate_raw, boundary_rate_shrunk,
    dot_rate_raw,      dot_rate_shrunk
    """
    # Only include balls the batter actually faced (excludes wides)
    faced = balls_df[balls_df["is_ball_faced"]].copy()

    # Mark boundaries
    faced["is_four"] = faced["runs_batter"] == 4
    faced["is_six"]  = faced["runs_batter"] == 6
    faced["is_dot"]  = faced["runs_batter"] == 0

    grp = faced.groupby(["batter_id", "phase"])

    raw = grp.agg(
        balls_faced   = ("is_ball_faced",  "sum"),
        runs          = ("runs_batter",    "sum"),
        dismissals    = ("is_dismissal",   "sum"),
        fours         = ("is_four",        "sum"),
        sixes         = ("is_six",         "sum"),
        dots          = ("is_dot",         "sum"),
    ).reset_index()

    # Raw rates
    raw["strike_rate_raw"]   = 100 * raw["runs"] / raw["balls_faced"].replace(0, np.nan)
    raw["avg_raw"]           = raw["runs"] / raw["dismissals"].replace(0, np.nan)
    raw["boundary_rate_raw"] = (raw["fours"] + raw["sixes"]) / raw["balls_faced"].replace(0, np.nan)
    raw["dot_rate_raw"]      = raw["dots"] / raw["balls_faced"].replace(0, np.nan)

    # League averages per phase (used as the shrinkage prior)
    league = (
        raw.groupby("phase")
        .apply(lambda g: pd.Series({
            "league_sr":   (100 * g["runs"].sum() / g["balls_faced"].sum()),
            "league_avg":  (g["runs"].sum() / g["dismissals"].sum()),
            "league_br":   ((g["fours"].sum() + g["sixes"].sum()) / g["balls_faced"].sum()),
            "league_dot":  (g["dots"].sum() / g["balls_faced"].sum()),
        }), include_groups=False)
        .reset_index()
    )
    raw = raw.merge(league, on="phase")

    n = raw["balls_faced"]

    raw["strike_rate_shrunk"]   = _shrink(raw["strike_rate_raw"].fillna(raw["league_sr"]),
                                          n, raw["league_sr"],  SHRINKAGE_K_BAT)
    raw["avg_shrunk"]           = _shrink(raw["avg_raw"].fillna(raw["league_avg"]),
                                          n, raw["league_avg"], SHRINKAGE_K_BAT)
    raw["boundary_rate_shrunk"] = _shrink(raw["boundary_rate_raw"].fillna(raw["league_br"]),
                                          n, raw["league_br"],  SHRINKAGE_K_BAT)
    raw["dot_rate_shrunk"]      = _shrink(raw["dot_rate_raw"].fillna(raw["league_dot"]),
                                          n, raw["league_dot"], SHRINKAGE_K_BAT)

    keep = [
        "batter_id", "phase",
        "balls_faced", "runs", "dismissals",
        "strike_rate_raw",   "strike_rate_shrunk",
        "avg_raw",           "avg_shrunk",
        "boundary_rate_raw", "boundary_rate_shrunk",
        "dot_rate_raw",      "dot_rate_shrunk",
    ]
    return raw[keep].sort_values(["batter_id", "phase"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Bowler features
# ---------------------------------------------------------------------------

def build_bowler_features(balls_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute bowling statistics grouped by (bowler_id, phase).

    Columns produced
    ----------------
    bowler_id, phase,
    balls_bowled, runs_conceded, wickets,
    economy_raw,      economy_shrunk,
    bowling_avg_raw,  bowling_avg_shrunk,
    dot_rate_raw,     dot_rate_shrunk,
    boundary_rate_raw, boundary_rate_shrunk   (boundaries conceded)
    """
    # All deliveries count for the bowler (wides and no-balls cost runs)
    b = balls_df.copy()
    b["is_four"]    = b["runs_batter"] == 4
    b["is_six"]     = b["runs_batter"] == 6
    b["is_dot_bowl"] = (b["runs_bowler"] == 0) & (~b["is_wide"])

    grp = b.groupby(["bowler_id", "phase"])

    raw = grp.agg(
        balls_bowled   = ("is_legal_ball", "sum"),   # legal balls only for economy
        deliveries     = ("match_id",      "count"), # total incl. wides/no-balls
        runs_conceded  = ("runs_bowler",   "sum"),
        wickets        = ("is_bowler_wicket", "sum"),
        fours_conceded = ("is_four",       "sum"),
        sixes_conceded = ("is_six",        "sum"),
        dots           = ("is_dot_bowl",   "sum"),
    ).reset_index()

    # Economy = runs per OVER (6 legal balls)
    raw["economy_raw"]       = 6 * raw["runs_conceded"] / raw["balls_bowled"].replace(0, np.nan)
    raw["bowling_avg_raw"]   = raw["runs_conceded"] / raw["wickets"].replace(0, np.nan)
    raw["boundary_rate_raw"] = ((raw["fours_conceded"] + raw["sixes_conceded"])
                                / raw["balls_bowled"].replace(0, np.nan))
    raw["dot_rate_raw"]      = raw["dots"] / raw["deliveries"].replace(0, np.nan)

    # League averages per phase
    league = (
        raw.groupby("phase")
        .apply(lambda g: pd.Series({
            "league_econ": 6 * g["runs_conceded"].sum() / g["balls_bowled"].sum(),
            "league_avg":  g["runs_conceded"].sum() / g["wickets"].sum(),
            "league_br":   ((g["fours_conceded"].sum() + g["sixes_conceded"].sum())
                            / g["balls_bowled"].sum()),
            "league_dot":  g["dots"].sum() / g["deliveries"].sum(),
        }), include_groups=False)
        .reset_index()
    )
    raw = raw.merge(league, on="phase")

    n = raw["balls_bowled"]

    raw["economy_shrunk"]       = _shrink(raw["economy_raw"].fillna(raw["league_econ"]),
                                          n, raw["league_econ"], SHRINKAGE_K_BOWL)
    raw["bowling_avg_shrunk"]   = _shrink(raw["bowling_avg_raw"].fillna(raw["league_avg"]),
                                          n, raw["league_avg"],  SHRINKAGE_K_BOWL)
    raw["boundary_rate_shrunk"] = _shrink(raw["boundary_rate_raw"].fillna(raw["league_br"]),
                                          n, raw["league_br"],   SHRINKAGE_K_BOWL)
    raw["dot_rate_shrunk"]      = _shrink(raw["dot_rate_raw"].fillna(raw["league_dot"]),
                                          n, raw["league_dot"],  SHRINKAGE_K_BOWL)

    keep = [
        "bowler_id", "phase",
        "balls_bowled", "runs_conceded", "wickets",
        "economy_raw",       "economy_shrunk",
        "bowling_avg_raw",   "bowling_avg_shrunk",
        "boundary_rate_raw", "boundary_rate_shrunk",
        "dot_rate_raw",      "dot_rate_shrunk",
    ]
    return raw[keep].sort_values(["bowler_id", "phase"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Convenience: build both at once
# ---------------------------------------------------------------------------

def build_all_features(
    balls_df: pd.DataFrame,
    matches_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build batter and bowler feature tables and return them."""
    log.info("Building batter features...")
    bat_df = build_batter_features(balls_df)
    log.info("  -> %d (batter_id, phase) rows", len(bat_df))

    log.info("Building bowler features...")
    bowl_df = build_bowler_features(balls_df)
    log.info("  -> %d (bowler_id, phase) rows", len(bowl_df))

    return bat_df, bowl_df


# ---------------------------------------------------------------------------
# Load pre-built features from disk
# ---------------------------------------------------------------------------

def load_features() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load batter and bowler feature tables from cache/."""
    if not BATTER_FEATURES_PATH.exists() or not BOWLER_FEATURES_PATH.exists():
        raise FileNotFoundError(
            "Feature files not found. Run:  python -m src.features"
        )
    return (
        pd.read_parquet(BATTER_FEATURES_PATH),
        pd.read_parquet(BOWLER_FEATURES_PATH),
    )


# ---------------------------------------------------------------------------
# Pretty summary printed when run directly
# ---------------------------------------------------------------------------

def _print_summary(bat_df: pd.DataFrame, bowl_df: pd.DataFrame) -> None:
    print(f"\n{'='*65}")
    print("BATTER FEATURES  –  top 10 by strike rate (powerplay, shrunk)")
    print(f"{'='*65}")
    pp = (bat_df[bat_df["phase"] == "powerplay"]
          .sort_values("strike_rate_shrunk", ascending=False)
          .head(10)[["batter_id", "balls_faced", "strike_rate_raw", "strike_rate_shrunk"]])
    print(pp.to_string(index=False))

    print(f"\n{'='*65}")
    print("BATTER FEATURES  –  top 10 by strike rate (death, shrunk)")
    print(f"{'='*65}")
    death = (bat_df[bat_df["phase"] == "death"]
             .sort_values("strike_rate_shrunk", ascending=False)
             .head(10)[["batter_id", "balls_faced", "strike_rate_raw", "strike_rate_shrunk"]])
    print(death.to_string(index=False))

    print(f"\n{'='*65}")
    print("BOWLER FEATURES  –  top 10 by economy (death, shrunk)")
    print(f"{'='*65}")
    bd = (bowl_df[bowl_df["phase"] == "death"]
          .sort_values("economy_shrunk")
          .head(10)[["bowler_id", "balls_bowled", "economy_raw", "economy_shrunk"]])
    print(bd.to_string(index=False))

    print(f"\n{'='*65}")
    print("League averages by phase")
    print(f"{'='*65}")
    for phase in PHASES:
        b = bat_df[bat_df["phase"] == phase]
        bw = bowl_df[bowl_df["phase"] == phase]
        total_balls = b["balls_faced"].sum()
        total_runs  = b["runs"].sum()
        total_wkts  = b["dismissals"].sum()
        sr   = 100 * total_runs / total_balls if total_balls else 0
        avg  = total_runs / total_wkts if total_wkts else 0
        econ = 6 * bw["runs_conceded"].sum() / bw["balls_bowled"].sum() if len(bw) else 0
        print(f"  {phase:<12}  SR={sr:.1f}  avg={avg:.1f}  economy={econ:.2f}")
    print("="*65)


# ---------------------------------------------------------------------------
# Entry point:  python -m src.features
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    log.info("Loading balls and matches from cache...")
    balls_df   = pd.read_parquet(BALL_TABLE_PATH)
    matches_df = pd.read_parquet(MATCH_TABLE_PATH)
    log.info("  %d deliveries, %d matches", len(balls_df), len(matches_df))

    bat_df, bowl_df = build_all_features(balls_df, matches_df)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    bat_df.to_parquet(BATTER_FEATURES_PATH, index=False)
    bowl_df.to_parquet(BOWLER_FEATURES_PATH, index=False)
    print(f"Saved -> {BATTER_FEATURES_PATH}")
    print(f"Saved -> {BOWLER_FEATURES_PATH}")

    _print_summary(bat_df, bowl_df)
