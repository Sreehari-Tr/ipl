# ipl_project — IPL Match Prediction System

> Built stage by stage. You are currently on **Stage 1: Setup & Inspect**.

## Quick start

```bash
# 1. Create and activate the virtual environment (already done once)
python -m venv venv
.\venv\Scripts\activate          # Windows PowerShell

# 2. Install dependencies
pip install pandas pyarrow rich thefuzz python-Levenshtein

# 3. Run the Stage-1 inspection script
python src/inspect_one.py                  # inspects the first match file
python src/inspect_one.py 335982           # or pick a specific match ID
```

## Project layout

```
ipl/
├── ipl_json/          ← raw Cricsheet IPL JSON files (one per match)
├── venv/              ← Python virtual environment
└── ipl_project/
    ├── README.md      ← this file
    ├── cache/         ← parquet caches created in Stage 2
    └── src/
        ├── config.py        Stage 1 – paths, constants, name maps
        ├── inspect_one.py   Stage 1 – learn the data structure
        ├── parse.py         Stage 2 – JSON → ball table + match table
        ├── players.py       Stage 3 – player ID registry, roles, stats
        ├── features.py      Stage 4 – recency, shrinkage, phase profiles
        ├── simulate.py      Stage 6 – Monte Carlo ball-by-ball engine
        ├── models.py        Stage 5 – Elo, team-level ML, calibration
        ├── predict.py       Stage 7 – predict_match() + CLI
        └── evaluate.py      Stage 6/7 – backtesting & metrics
```

## Stages roadmap

| # | Stage | What you learn |
|---|-------|----------------|
| 1 | Setup + inspect | JSON structure, IDs, extras, quirks |
| 2 | Parse all matches | Ball table + match table, parquet cache |
| 3 | Player IDs & roles | Registry, positions, no-leakage stats |
| 4 | Phase profiles | Recency weighting + shrinkage |
| 5 | Baseline model | Elo, form, venue — honest evaluation |
| 6 | Simulator | Ball-by-ball Monte Carlo + per-player outputs |
| 7 | predict_match() | Full pipeline + backtest report |
| 8 | Calibration | Reliability curves, improvements |

## Key design decisions explained simply

### Why use player IDs instead of names?
A cricketer's name can be spelled differently across seasons ("V Kohli" vs
"Virat Kohli"). The `registry.people` field gives every player a fixed 8-character
ID that never changes.

### What is "shrinkage"?
If a player has faced only 20 balls in the data, their average is noisy.
We blend it toward the league average using the formula:
```
adjusted_average = (player_runs + k × league_avg) / (player_balls + k)
```
`k = 50` by default. With 20 balls the player's own data gets 20/70 = 29% weight;
with 200 balls it gets 200/250 = 80% weight.

### What is "recency weighting"?
A match from 2008 tells us less about today's player than a match from last week.
Each match gets weight `0.97 ^ rank` (where rank=0 is the most recent match).
Fifty matches ago → weight ≈ 0.22.

### What is Monte Carlo simulation?
Instead of predicting one single score, we simulate a whole match 5,000 times,
each time drawing random outcomes ball by ball. The distribution of those 5,000
results gives us not just a predicted score but also a confidence range (e.g. the
10th–90th percentile) and a win probability.
