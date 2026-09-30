"""
predict.py – Stage 6
=====================
Uses the MatchSimulator to play out an upcoming match thousands of times
and calculates the win probabilities and average scores.

We dynamically extract the most regular players for any two teams
and let them play against each other.

Run with:
    python -m src.predict
"""

import logging
from collections import Counter
import pandas as pd
from tqdm import tqdm

from src.config import BALL_TABLE_PATH, N_SIMULATIONS
from src.features import load_features
from src.models import load_model
from src.simulate import MatchSimulator

log = logging.getLogger(__name__)


def get_typical_lineup(team_name: str, balls_df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """
    Finds the most frequent batters and bowlers for a given team 
    based on the historical ball-by-ball data.
    """
    # 1. Batters
    team_batting = balls_df[balls_df["batting_team"] == team_name]
    top_batters = team_batting["batter_id"].value_counts().head(11).index.tolist()
    
    # 2. Bowlers
    team_bowling = balls_df[balls_df["bowling_team"] == team_name]
    top_bowlers = team_bowling["bowler_id"].value_counts().head(6).index.tolist()
    
    return top_batters, top_bowlers


def get_player_name(player_id: str, balls_df: pd.DataFrame) -> str:
    """Helper to get a human-readable name for an ID."""
    match = balls_df[balls_df["batter_id"] == player_id]
    if len(match):
        return match.iloc[0]["batter"]
    match = balls_df[balls_df["bowler_id"] == player_id]
    if len(match):
        return match.iloc[0]["bowler"]
    return player_id


def predict_match(team1: str, team2: str, n_sims: int = N_SIMULATIONS):
    """
    Run N simulations between two teams. Team1 bats first.
    """
    log.info("Loading models, features, and historical data...")
    model, classes = load_model()
    bat_df, bowl_df = load_features()
    balls = pd.read_parquet(BALL_TABLE_PATH)
    
    sim = MatchSimulator(model, classes, bat_df, bowl_df)
    
    log.info(f"Extracting lineups for {team1} and {team2}...")
    t1_batters, t1_bowlers = get_typical_lineup(team1, balls)
    t2_batters, t2_bowlers = get_typical_lineup(team2, balls)
    
    log.info(f"Team 1 ({team1}) Batters: {[get_player_name(pid, balls) for pid in t1_batters]}")
    log.info(f"Team 2 ({team2}) Bowlers: {[get_player_name(pid, balls) for pid in t2_bowlers]}")
    
    log.info(f"\nSimulating {n_sims} matches between {team1} and {team2}...")
    
    t1_wins = 0
    t2_wins = 0
    ties = 0
    first_innings_scores = []
    
    for _ in tqdm(range(n_sims), desc="Simulating"):
        # Innings 1: Team 1 bats, Team 2 bowls
        inn1 = sim.simulate_innings(t1_batters, t2_bowlers)
        t1_score = inn1["runs"]
        first_innings_scores.append(t1_score)
        
        # Innings 2: Team 2 bats, Team 1 bowls (chasing T1 score + 1)
        inn2 = sim.simulate_innings(t2_batters, t1_bowlers, target=t1_score + 1)
        t2_score = inn2["runs"]
        
        if t2_score > t1_score:
            t2_wins += 1
        elif t1_score > t2_score:
            t1_wins += 1
        else:
            ties += 1

    print("\n" + "="*50)
    print(f"PREDICTION RESULTS: {team1} vs {team2}")
    print("="*50)
    print(f"Total Simulations: {n_sims}")
    print(f"Average First Innings Score ({team1}): {sum(first_innings_scores)/n_sims:.1f}")
    
    p_t1 = (t1_wins / n_sims) * 100
    p_t2 = (t2_wins / n_sims) * 100
    p_tie = (ties / n_sims) * 100
    
    print(f"\nWin Probability:")
    print(f"  {team1:<25}: {p_t1:>5.1f}%")
    print(f"  {team2:<25}: {p_t2:>5.1f}%")
    print(f"  Tie                      : {p_tie:>5.1f}%")
    print("="*50)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # You can change these to any valid normalized team names
    predict_match("Chennai Super Kings", "Mumbai Indians", n_sims=1000)
