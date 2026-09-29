"""
config.py
=========
Single source of truth for all project-wide constants.
Nothing in this file computes anything — it's purely configuration.

Rule: import config, never hard-code paths or team names elsewhere.
"""

from pathlib import Path

# ── Directory layout ──────────────────────────────────────────────────────────
ROOT_DIR   = Path(__file__).resolve().parent.parent          # ipl_project/
DATA_DIR   = ROOT_DIR.parent / "ipl_json"                    # ../ipl_json/
CACHE_DIR  = ROOT_DIR / "cache"                              # ipl_project/cache/
CACHE_DIR.mkdir(parents=True, exist_ok=True)

BALL_TABLE_PATH  = CACHE_DIR / "balls.parquet"
MATCH_TABLE_PATH = CACHE_DIR / "matches.parquet"

# ── Game constants ────────────────────────────────────────────────────────────
BALLS_PER_OVER          = 6
MAX_BOWLER_OVERS        = 4
POWERPLAY_OVERS         = range(0, 6)    # over indices 0-5  (overs 1-6)
MIDDLE_OVERS            = range(6, 15)   # over indices 6-14 (overs 7-15)
DEATH_OVERS             = range(15, 20)  # over indices 15-19 (overs 16-20)

# ── Shrinkage / recency hyper-parameters ─────────────────────────────────────
# k controls the pull toward the league average.
# If a batter has faced fewer than k balls, predictions lean heavily on the
# league average; once they have many more balls, their own stats dominate.
SHRINKAGE_K_BAT   = 50    # balls needed before personal batting stats dominate
SHRINKAGE_K_BOWL  = 60    # balls needed before personal bowling stats dominate

# Exponential decay: weight of a match = DECAY_ALPHA ^ (rank_from_most_recent)
# 0.97 means match played 50 matches ago has weight 0.97^50 ≈ 0.22
RECENCY_DECAY_ALPHA = 0.97

# ── Team name normalisation ───────────────────────────────────────────────────
# All spelling variants → canonical current name
TEAM_NAME_MAP: dict[str, str] = {
    # Delhi
    "Delhi Daredevils"                  : "Delhi Capitals",
    "Delhi Capitals"                    : "Delhi Capitals",

    # Punjab
    "Kings XI Punjab"                   : "Punjab Kings",
    "Punjab Kings"                      : "Punjab Kings",

    # Hyderabad
    "Deccan Chargers"                   : "Sunrisers Hyderabad",
    "Sunrisers Hyderabad"               : "Sunrisers Hyderabad",

    # Bangalore
    "Royal Challengers Bangalore"       : "Royal Challengers Bengaluru",
    "Royal Challengers Bengaluru"       : "Royal Challengers Bengaluru",

    # Rest (kept for completeness)
    "Chennai Super Kings"               : "Chennai Super Kings",
    "Mumbai Indians"                    : "Mumbai Indians",
    "Kolkata Knight Riders"             : "Kolkata Knight Riders",
    "Rajasthan Royals"                  : "Rajasthan Royals",
    "Lucknow Super Giants"              : "Lucknow Super Giants",
    "Gujarat Titans"                    : "Gujarat Titans",
    "Rising Pune Supergiants"           : "Rising Pune Supergiants",
    "Rising Pune Supergiant"            : "Rising Pune Supergiants",
    "Pune Warriors"                     : "Pune Warriors",
    "Kochi Tuskers Kerala"              : "Kochi Tuskers Kerala",
}

# ── Venue normalisation ───────────────────────────────────────────────────────
VENUE_NAME_MAP: dict[str, str] = {
    # Wankhede
    "Wankhede Stadium"                          : "Wankhede Stadium",
    "Wankhede Stadium, Mumbai"                  : "Wankhede Stadium",
    # Chinnaswamy
    "M Chinnaswamy Stadium"                     : "M Chinnaswamy Stadium",
    "M.Chinnaswamy Stadium"                     : "M Chinnaswamy Stadium",
    "M Chinnaswamy Stadium, Bengaluru"          : "M Chinnaswamy Stadium",
    # Eden Gardens
    "Eden Gardens"                              : "Eden Gardens",
    "Eden Gardens, Kolkata"                     : "Eden Gardens",
    # Feroz Shah Kotla / Arun Jaitley
    "Feroz Shah Kotla"                          : "Arun Jaitley Stadium",
    "Feroz Shah Kotla Ground"                   : "Arun Jaitley Stadium",
    "Arun Jaitley Stadium"                      : "Arun Jaitley Stadium",
    "Arun Jaitley Stadium, Delhi"               : "Arun Jaitley Stadium",
    # MA Chidambaram
    "MA Chidambaram Stadium"                    : "MA Chidambaram Stadium",
    "MA Chidambaram Stadium, Chepauk"           : "MA Chidambaram Stadium",
    "MA Chidambaram Stadium, Chepauk, Chennai"  : "MA Chidambaram Stadium",
    # Rajiv Gandhi
    "Rajiv Gandhi International Stadium"        : "Rajiv Gandhi International Stadium",
    "Rajiv Gandhi International Stadium, Uppal" : "Rajiv Gandhi International Stadium",
    "Rajiv Gandhi International Cricket Stadium": "Rajiv Gandhi International Stadium",
    # Sawai Mansingh
    "Sawai Mansingh Stadium"                    : "Sawai Mansingh Stadium",
    "Sawai Mansingh Stadium, Jaipur"            : "Sawai Mansingh Stadium",
    # Punjab Cricket Association
    "Punjab Cricket Association Stadium"        : "Punjab Cricket Association Stadium",
    "Punjab Cricket Association IS Bindra Stadium": "Punjab Cricket Association Stadium",
    "Punjab Cricket Association IS Bindra Stadium, Mohali": "Punjab Cricket Association Stadium",
    # DY Patil
    "DY Patil Stadium"                          : "DY Patil Stadium",
    "Dr DY Patil Sports Academy"                : "DY Patil Stadium",
    # Brabourne
    "Brabourne Stadium"                         : "Brabourne Stadium",
    "Brabourne Stadium, Mumbai"                 : "Brabourne Stadium",
    # Narendra Modi / Sardar Patel
    "Narendra Modi Stadium"                     : "Narendra Modi Stadium",
    "Sardar Patel Stadium"                      : "Narendra Modi Stadium",
    # Ekana
    "BRSABV Ekana Cricket Stadium"              : "Ekana Cricket Stadium",
    "Ekana Cricket Stadium"                     : "Ekana Cricket Stadium",
}

# ── Bowling type heuristics ───────────────────────────────────────────────────
KNOWN_SPINNERS: frozenset[str] = frozenset()  # populated later from player profiles

# ── Simulation parameters ─────────────────────────────────────────────────────
N_SIMULATIONS = 5_000
RANDOM_SEED   = 42

# ── Impact Player rule ────────────────────────────────────────────────────────
IMPACT_PLAYER_SEASON_START = "2023"
MAX_IMPACT_SUBSTITUTES     = 5
