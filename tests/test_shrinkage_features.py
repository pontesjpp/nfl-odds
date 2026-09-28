"""Unit tests verifying starter-isolated Bayesian shrinkage in build_features."""

import polars as pl
import pytest
from nfl_odds.features.build_features import _apply_shrinkage


def test_qb_starter_shrinkage_avoids_backup_distortion():
    """Verify that backup QBs (kneeldowns/garbage time) do not drag down starting QBs."""
    data = {
        "player_id": ["QB_STARTER_1", "QB_STARTER_2", "QB_BACKUP_1", "QB_BACKUP_2"],
        "position": ["QB", "QB", "QB", "QB"],
        "season": [2026, 2026, 2026, 2026],
        "week": [3, 3, 3, 3],
        "games_played_sample_size": [2, 2, 2, 2],
        "passing_yards_season_avg": [260.0, 240.0, 4.0, 0.0],
        "attempts_season_avg": [34.0, 30.0, 1.0, 0.0],
    }
    df = pl.DataFrame(data)

    shrunk_df = _apply_shrinkage(df, "passing_yards", k=2.0)

    # Positional mean for starters should reflect starters (~250), NOT all 4 QBs (126.0)
    pos_mean = shrunk_df["passing_yards_pos_mean"][0]
    assert pos_mean >= 240.0, f"Expected QB starter pos_mean >= 240.0, got: {pos_mean}"

    starter_1_shrunk = shrunk_df.filter(pl.col("player_id") == "QB_STARTER_1")["passing_yards_shrunk_season_avg"][0]
    assert starter_1_shrunk >= 245.0, f"Starter QB shrunk avg distorted downward: {starter_1_shrunk}"


def test_rb_starter_shrinkage():
    """Verify that RB shrinkage uses rotation RBs and does not drag starter down with 0-carry RBs."""
    data = {
        "player_id": ["RB_LEAD", "RB_BACKUP_0_CARRIES"],
        "position": ["RB", "RB"],
        "season": [2026, 2026],
        "week": [3, 3],
        "games_played_sample_size": [2, 2],
        "rushing_yards_season_avg": [80.0, 0.0],
        "carries_season_avg": [18.0, 0.0],
    }
    df = pl.DataFrame(data)

    shrunk_df = _apply_shrinkage(df, "rushing_yards", k=2.0)
    pos_mean = shrunk_df["rushing_yards_pos_mean"][0]
    assert pos_mean >= 70.0, f"Expected RB pos_mean >= 70.0, got: {pos_mean}"


def test_shrinkage_graceful_fallback():
    """Verify fallback to all-player mean when no starter threshold is met."""
    data = {
        "player_id": ["QB_LOW_ATT"],
        "position": ["QB"],
        "season": [2026],
        "week": [1],
        "games_played_sample_size": [1],
        "passing_yards_season_avg": [45.0],
        "attempts_season_avg": [5.0],
    }
    df = pl.DataFrame(data)

    shrunk_df = _apply_shrinkage(df, "passing_yards", k=2.0)
    assert not shrunk_df["passing_yards_shrunk_season_avg"].is_null().any()
    assert shrunk_df["passing_yards_shrunk_season_avg"][0] == 45.0
