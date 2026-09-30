"""
api.py
=======
FastAPI backend to serve the React frontend simulator.
"""

import logging
from typing import List, Optional
from collections import Counter
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from tqdm import tqdm

from src.config import BALL_TABLE_PATH, MATCH_TABLE_PATH
from src.features import load_features
from src.models import load_model
from src.simulate import MatchSimulator
from src.predict import get_player_name

log = logging.getLogger(__name__)

app = FastAPI()

# Allow CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables to hold data in memory
balls_df = None
matches_df = None
bat_df = None
bowl_df = None
sim = None
player_names = {}

@app.on_event("startup")
def load_data():
    global balls_df, matches_df, bat_df, bowl_df, sim, player_names
    log.info("Loading models and tables into memory...")
    balls_df = pd.read_parquet(BALL_TABLE_PATH)
    matches_df = pd.read_parquet(MATCH_TABLE_PATH)
    model, classes = load_model()
    bat_df, bowl_df = load_features()
    sim = MatchSimulator(model, classes, bat_df, bowl_df)
    
    # Pre-populate global player names
    batters = balls_df.groupby("batter_id")["batter"].first().to_dict()
    bowlers = balls_df.groupby("bowler_id")["bowler"].first().to_dict()
    player_names.update(batters)
    player_names.update(bowlers)
    
    log.info("Data loaded successfully.")

@app.get("/api/metadata")
def get_metadata():
    """Return all known teams and venues."""
    teams = pd.concat([matches_df["team1"], matches_df["team2"]]).unique().tolist()
    venues = matches_df["venue"].dropna().unique().tolist()
    return {
        "teams": sorted([t for t in teams if t]),
        "venues": sorted([v for v in venues if v])
    }

@app.get("/api/players")
def get_all_players():
    """Return the top 300 batters and top 200 bowlers globally."""
    batters_counts = balls_df.groupby("batter_id")["batter"].first().to_dict()
    batter_frequencies = balls_df["batter_id"].value_counts().head(300).index.tolist()
    
    batters = [{"id": pid, "name": batters_counts[pid]} for pid in batter_frequencies]
    
    bowlers_counts = balls_df.groupby("bowler_id")["bowler"].first().to_dict()
    bowler_frequencies = balls_df["bowler_id"].value_counts().head(200).index.tolist()
    
    bowlers = [{"id": pid, "name": bowlers_counts[pid]} for pid in bowler_frequencies]
    
    # Sort alphabetically by name
    batters = sorted(batters, key=lambda x: x["name"])
    bowlers = sorted(bowlers, key=lambda x: x["name"])
    
    return {
        "batters": batters,
        "bowlers": bowlers
    }

@app.get("/api/players/{team}")
def get_players(team: str):
    """Return the most frequent batters and bowlers for a given team."""
    team_batters_df = balls_df[balls_df["batting_team"] == team]
    batters_counts = team_batters_df.groupby("batter_id")["batter"].first().to_dict()
    batter_frequencies = team_batters_df["batter_id"].value_counts().head(20).index.tolist()
    
    batters = [{"id": pid, "name": batters_counts[pid]} for pid in batter_frequencies]
    
    team_bowlers_df = balls_df[balls_df["bowling_team"] == team]
    bowlers_counts = team_bowlers_df.groupby("bowler_id")["bowler"].first().to_dict()
    bowler_frequencies = team_bowlers_df["bowler_id"].value_counts().head(12).index.tolist()
    
    bowlers = [{"id": pid, "name": bowlers_counts[pid]} for pid in bowler_frequencies]
    
    return {
        "batters": batters,
        "bowlers": bowlers
    }

class SimulateRequest(BaseModel):
    team1: str
    team2: str
    venue: str
    team1_batters: List[str]
    team1_bowlers: List[str]
    team2_batters: List[str]
    team2_bowlers: List[str]
    n_sims: Optional[int] = 100

def generate_scorecard(innings_log: List[dict], p_names: dict) -> dict:
    batting = {}
    bowling = {}
    for b in innings_log:
        bat = b["batter"]
        bowl = b["bowler"]
        out = b["outcome"]
        
        if bat not in batting:
            batting[bat] = {"name": p_names.get(bat, bat), "runs": 0, "balls": 0, "fours": 0, "sixes": 0, "out": False}
        if bowl not in bowling:
            bowling[bowl] = {"name": p_names.get(bowl, bowl), "overs": "", "balls": 0, "runs": 0, "wickets": 0}
            
        is_legal = out not in ["Wd", "Nb"]
        
        if out not in ["Wd"]:
            batting[bat]["balls"] += 1
            
        if out == "W":
            batting[bat]["out"] = True
            if is_legal:
                bowling[bowl]["balls"] += 1
                bowling[bowl]["wickets"] += 1
        elif out in ["Wd", "Nb"]:
            bowling[bowl]["runs"] += 1
        else:
            runs = int(out)
            batting[bat]["runs"] += runs
            bowling[bowl]["runs"] += runs
            if runs == 4:
                batting[bat]["fours"] += 1
            if runs == 6:
                batting[bat]["sixes"] += 1
            if is_legal:
                bowling[bowl]["balls"] += 1

    for b_id, stats in bowling.items():
        stats["overs"] = f"{stats['balls'] // 6}.{stats['balls'] % 6}"
        
    return {"batting": list(batting.values()), "bowling": list(bowling.values())}

@app.post("/api/simulate")
def simulate_match(req: SimulateRequest):
    t1_wins = 0
    t2_wins = 0
    ties = 0
    t1_scores = []
    
    sample_match = None
    
    for i in range(req.n_sims):
        # Innings 1
        inn1 = sim.simulate_innings(req.team1_batters, req.team2_bowlers)
        t1_score = inn1["runs"]
        t1_scores.append(t1_score)
        
        # Innings 2
        inn2 = sim.simulate_innings(req.team2_batters, req.team1_bowlers, target=t1_score + 1)
        t2_score = inn2["runs"]
        
        if t2_score > t1_score:
            t2_wins += 1
        elif t1_score > t2_score:
            t1_wins += 1
        else:
            ties += 1
            
        if i == req.n_sims - 1:
            sample_match = {
                "inn1_runs": inn1["runs"],
                "inn1_wickets": inn1["wickets"],
                "inn2_runs": inn2["runs"],
                "inn2_wickets": inn2["wickets"],
                "inn2_overs": inn2["overs"],
                "inn2_balls": inn2["balls"],
                "inn1_scorecard": generate_scorecard(inn1["log"], player_names),
                "inn2_scorecard": generate_scorecard(inn2["log"], player_names),
            }

    return {
        "team1_win_prob": round((t1_wins / req.n_sims) * 100, 1),
        "team2_win_prob": round((t2_wins / req.n_sims) * 100, 1),
        "tie_prob": round((ties / req.n_sims) * 100, 1),
        "avg_t1_score": round(sum(t1_scores) / req.n_sims, 1),
        "sample_match": sample_match
    }
