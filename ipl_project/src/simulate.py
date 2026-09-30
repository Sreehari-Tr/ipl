"""
simulate.py – Stage 5
======================
Simulates a single T20 innings or a full match ball-by-ball.
We use the XGBoost model trained in Stage 4 to predict the outcome of each delivery,
managing cricket logic like strike rotation, bowler spells, and phases.

Public API
----------
    simulate_innings(...) -> dict
    simulate_match(...)   -> dict

Run `python -m src.simulate` to see a quick demo simulation!
"""

import logging
import random
import numpy as np
import pandas as pd

from src.config import POWERPLAY_OVERS, MIDDLE_OVERS, DEATH_OVERS
from src.features import load_features, PHASES
from src.models import load_model

log = logging.getLogger(__name__)


def _get_phase(over_idx: int) -> str:
    """Return the phase for a given over index (0-19)."""
    if over_idx in POWERPLAY_OVERS:
        return "powerplay"
    if over_idx in MIDDLE_OVERS:
        return "middle"
    return "death"


class MatchSimulator:
    def __init__(self, model, classes, bat_df, bowl_df):
        self.model = model
        self.classes = classes
        
        # Convert feature DataFrames to dictionaries for blazing fast lookups
        # Format: {(player_id, phase): row_dict}
        self.bat_stats = bat_df.set_index(["batter_id", "phase"]).to_dict("index")
        self.bowl_stats = bowl_df.set_index(["bowler_id", "phase"]).to_dict("index")
        
        # Cache league averages in case a player is completely unseen
        self.league_bat = {
            phase: bat_df[bat_df["phase"] == phase].mean(numeric_only=True).to_dict()
            for phase in PHASES
        }
        self.league_bowl = {
            phase: bowl_df[bowl_df["phase"] == phase].mean(numeric_only=True).to_dict()
            for phase in PHASES
        }

    def _get_features(self, batter_id: str, bowler_id: str, phase: str) -> np.ndarray:
        """Extract the exact feature array required by the XGBoost model."""
        # 1. Batter stats
        b_stat = self.bat_stats.get((batter_id, phase), self.league_bat[phase])
        bat_sr = b_stat.get("strike_rate_shrunk", self.league_bat[phase]["strike_rate_shrunk"])
        bat_avg = b_stat.get("avg_shrunk", self.league_bat[phase]["avg_shrunk"])
        
        # 2. Bowler stats
        bw_stat = self.bowl_stats.get((bowler_id, phase), self.league_bowl[phase])
        bowl_econ = bw_stat.get("economy_shrunk", self.league_bowl[phase]["economy_shrunk"])
        bowl_avg = bw_stat.get("bowling_avg_shrunk", self.league_bowl[phase]["bowling_avg_shrunk"])
        
        # 3. Phase OHE (Powerplay, Middle, Death)
        p_pp = 1.0 if phase == "powerplay" else 0.0
        p_mid = 1.0 if phase == "middle" else 0.0
        p_death = 1.0 if phase == "death" else 0.0
        
        # Must match training order: 
        # strike_rate_shrunk, avg_shrunk, economy_shrunk, bowling_avg_shrunk, phase_powerplay, phase_middle, phase_death
        return np.array([[bat_sr, bat_avg, bowl_econ, bowl_avg, p_pp, p_mid, p_death]])

    def simulate_ball(self, batter_id: str, bowler_id: str, phase: str) -> str:
        """Predict the outcome of a single delivery."""
        X = self._get_features(batter_id, bowler_id, phase)
        probs = self.model.predict_proba(X)[0]
        
        # Roll a weighted die to pick the outcome
        outcome = np.random.choice(self.classes, p=probs)
        return outcome

    def simulate_innings(self, batting_lineup: list[str], bowling_lineup: list[str], target: int = None) -> dict:
        """
        Simulate a 20-over innings.
        Batting lineup: list of 11 batter IDs
        Bowling lineup: list of 5-6 bowler IDs
        target: Optional score to chase. Innings ends if runs >= target.
        """
        runs = 0
        wickets = 0
        legal_balls = 0
        
        striker_idx = 0
        non_striker_idx = 1
        next_batter_idx = 2
        
        # Track bowler usage: dict of {bowler_id: legal_balls_bowled}
        bowler_balls = {b: 0 for b in bowling_lineup}
        last_bowler = None
        
        ball_by_ball_log = []

        while legal_balls < 120 and wickets < 10:
            if target is not None and runs >= target:
                break
            
            over_idx = legal_balls // 6
            phase = _get_phase(over_idx)
            
            # Simple Bowler Selection: pick someone who hasn't bowled 24 balls (4 overs)
            # and isn't the one who bowled the previous over.
            available_bowlers = [b for b, balls in bowler_balls.items() if balls < 24 and b != last_bowler]
            if not available_bowlers:
                available_bowlers = [b for b, balls in bowler_balls.items() if balls < 24]
                
            if not available_bowlers: # Fallback if somehow all bowled out
                available_bowlers = bowling_lineup
                
            current_bowler = random.choice(available_bowlers)
            striker = batting_lineup[striker_idx]
            
            outcome = self.simulate_ball(striker, current_bowler, phase)
            
            # Process outcome
            is_legal = True
            runs_on_ball = 0
            is_wicket = False
            extras = 0
            
            if outcome == "W":
                wickets += 1
                is_wicket = True
                striker_idx = next_batter_idx
                next_batter_idx += 1
            elif outcome == "Wd" or outcome == "Nb":
                is_legal = False
                extras = 1
                runs += 1 # Penalty run for wide/no-ball
            else:
                runs_on_ball = int(outcome)
                runs += runs_on_ball
                
                # Strike rotation on 1 or 3
                if runs_on_ball % 2 != 0:
                    striker_idx, non_striker_idx = non_striker_idx, striker_idx

            if is_legal:
                legal_balls += 1
                bowler_balls[current_bowler] += 1
                
                # Over complete -> rotate strike and switch bowler
                if legal_balls % 6 == 0:
                    striker_idx, non_striker_idx = non_striker_idx, striker_idx
                    last_bowler = current_bowler
            
            ball_by_ball_log.append({
                "over": over_idx,
                "ball": (legal_balls % 6) if is_legal else (legal_balls % 6) + 1, # approximation for logging
                "batter": striker,
                "bowler": current_bowler,
                "outcome": outcome,
                "total_runs": runs,
                "total_wickets": wickets
            })

        return {
            "runs": runs,
            "wickets": wickets,
            "overs": legal_balls // 6,
            "balls": legal_balls % 6,
            "log": ball_by_ball_log
        }


def run_demo():
    """Run a quick demo to ensure the simulator works."""
    log.info("Loading models and features...")
    model, classes = load_model()
    bat_df, bowl_df = load_features()
    
    sim = MatchSimulator(model, classes, bat_df, bowl_df)
    
    # Pick top 11 batters by volume for team 1
    top_batters = bat_df.groupby("batter_id")["balls_faced"].sum().sort_values(ascending=False).index.tolist()
    batting_team = top_batters[:11]
    
    # Pick top 6 bowlers by volume for team 2
    top_bowlers = bowl_df.groupby("bowler_id")["balls_bowled"].sum().sort_values(ascending=False).index.tolist()
    bowling_team = top_bowlers[:6]
    
    log.info("Simulating an innings...")
    result = sim.simulate_innings(batting_team, bowling_team)
    
    print("\n" + "="*50)
    print("SIMULATION RESULT")
    print("="*50)
    print(f"Total Score: {result['runs']}/{result['wickets']}")
    print(f"Overs: {result['overs']}.{result['balls']}")
    print("="*50)
    
    print("\nLast 5 balls of the innings:")
    for b in result['log'][-5:]:
        print(f"Over {b['over']}.{b['ball']} | {b['batter'][:8]} vs {b['bowler'][:8]} -> Result: {b['outcome']}")
    print("="*50 + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_demo()
