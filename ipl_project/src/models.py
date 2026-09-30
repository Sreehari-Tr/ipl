"""
models.py – Stage 4
====================
Trains a ball-by-ball predictive model using XGBoost.

We join the historical deliveries (balls.parquet) with the shrunk player features
(batter_features.parquet, bowler_features.parquet). Then we train a classifier
to predict the outcome of any given delivery.

Possible outcomes:
    '0', '1', '2', '3', '4', '6', 'W' (Wicket), 'Wd' (Wide), 'Nb' (No-ball)

Features used:
    - Batter shrunk SR and Average
    - Bowler shrunk Economy and Average
    - Phase (powerplay / middle / death)

Outputs:
    cache/xgb_model.json    – The trained XGBoost model
    cache/classes.json      – The mapping of classes
"""

import json
import logging
import pickle
from pathlib import Path

import pandas as pd
import numpy as np
import xgboost as xgb

from src.config import (
    BALL_TABLE_PATH,
    CACHE_DIR,
)
from src.features import BATTER_FEATURES_PATH, BOWLER_FEATURES_PATH

log = logging.getLogger(__name__)

MODEL_PATH = CACHE_DIR / "xgb_model.json"
CLASSES_PATH = CACHE_DIR / "classes.json"


def _create_target(row: pd.Series) -> str:
    """Map a delivery row to one of our target classes."""
    if row["is_wide"]:
        return "Wd"
    if row["is_noball"]:
        return "Nb"
    if row["is_dismissal"]:
        return "W"
    
    runs = int(row["runs_batter"])
    if runs == 5:
        return "4"  # Very rare, group with 4
    if runs > 6:
        return "6"
    return str(runs)


def prepare_training_data() -> tuple[pd.DataFrame, pd.Series]:
    """Load balls and features, merge them, and extract X and y."""
    log.info("Loading tables...")
    balls = pd.read_parquet(BALL_TABLE_PATH)
    bat_f = pd.read_parquet(BATTER_FEATURES_PATH)
    bowl_f = pd.read_parquet(BOWLER_FEATURES_PATH)

    log.info("Merging features with deliveries...")
    # Join batter features
    df = balls.merge(
        bat_f[["batter_id", "phase", "strike_rate_shrunk", "avg_shrunk"]],
        on=["batter_id", "phase"],
        how="inner"
    )
    # Join bowler features
    df = df.merge(
        bowl_f[["bowler_id", "phase", "economy_shrunk", "bowling_avg_shrunk"]],
        on=["bowler_id", "phase"],
        how="inner"
    )

    log.info("Creating target column...")
    # Use pandas apply to map outcomes
    df["target"] = df.apply(_create_target, axis=1)

    log.info("Encoding categorical features...")
    # One-hot encode the phase
    df = pd.get_dummies(df, columns=["phase"], drop_first=False)
    # Ensure all three phases exist even if one is missing in a tiny test split
    for col in ["phase_powerplay", "phase_middle", "phase_death"]:
        if col not in df.columns:
            df[col] = 0
            
    # Convert booleans to int just in case
    df["phase_powerplay"] = df["phase_powerplay"].astype(int)
    df["phase_middle"] = df["phase_middle"].astype(int)
    df["phase_death"] = df["phase_death"].astype(int)

    feature_cols = [
        "strike_rate_shrunk", "avg_shrunk",
        "economy_shrunk", "bowling_avg_shrunk",
        "phase_powerplay", "phase_middle", "phase_death"
    ]
    
    X = df[feature_cols]
    y = df["target"]
    return X, y


def train_model() -> None:
    """Train the XGBoost classifier and save it."""
    X, y = prepare_training_data()

    # Get unique classes and map them to integers for XGBoost
    classes = sorted(y.unique().tolist())
    class_to_idx = {c: i for i, c in enumerate(classes)}
    y_encoded = y.map(class_to_idx)

    log.info(f"Target classes found: {classes}")
    log.info("Training XGBoost Multi-class model (this may take a minute)...")
    
    # We use a modest number of estimators so it doesn't take forever,
    # but enough to learn the interactions.
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        objective="multi:softprob",
        num_class=len(classes),
        random_state=42,
        n_jobs=-1
    )
    
    model.fit(X, y_encoded)
    log.info("Training complete.")

    # Save model and classes
    model.save_model(MODEL_PATH)
    with open(CLASSES_PATH, "w") as f:
        json.dump(classes, f)
        
    log.info(f"Saved model to {MODEL_PATH}")
    log.info(f"Saved classes to {CLASSES_PATH}")
    
    # Feature importances
    log.info("\nFeature Importances:")
    importances = model.feature_importances_
    for col, imp in zip(X.columns, importances):
        log.info(f"  {col:<20}: {imp:.4f}")


def load_model() -> tuple[xgb.XGBClassifier, list[str]]:
    """Load the trained model and class list."""
    if not MODEL_PATH.exists() or not CLASSES_PATH.exists():
        raise FileNotFoundError("Model not found. Run: python -m src.models")
        
    with open(CLASSES_PATH, "r") as f:
        classes = json.load(f)
        
    model = xgb.XGBClassifier()
    model.load_model(MODEL_PATH)
    return model, classes


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    train_model()
