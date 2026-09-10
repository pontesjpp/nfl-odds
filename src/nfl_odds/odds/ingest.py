import polars as pl
import numpy as np

def generate_mock_odds(df_games: pl.DataFrame, target_stat: str = "rushing_yards") -> pl.DataFrame:
    """
    Generate mock odds around the actual realized stats to simulate a bookmaker for backtesting.
    This is for MVP purposes only.
    """
    # Let's say bookmakers are decent at predicting, so the line is actual + noise
    # We shouldn't use actual to generate the line exactly, because that's data leakage if the model is testing.
    # But for a dummy odds dataset, we'll just use a rolling average of the player as the "line".
    
    # We assume df_games has 'player_id', 'game_id', 'season', 'week', and f'{target_stat}_avg_5'
    
    avg_col = f"{target_stat}_avg_5"
    if avg_col not in df_games.columns:
        # fallback
        lines = np.random.normal(50, 15, len(df_games))
    else:
        lines = df_games[avg_col].to_numpy() + np.random.normal(0, 5, len(df_games))
        
    lines = np.round(lines * 2) / 2  # round to .5
    lines = np.clip(lines, 10.5, 150.5)
    
    # odds are usually 1.85 to 1.90 on both sides
    odds_over = np.random.uniform(1.85, 1.95, len(df_games))
    odds_under = 3.75 - odds_over # approx
    
    odds_df = pl.DataFrame({
        "player_id": df_games["player_id"],
        "season": df_games["season"],
        "week": df_games["week"],
        "market": [target_stat] * len(df_games),
        "line": lines,
        "odds_over": np.round(odds_over, 2),
        "odds_under": np.round(odds_under, 2),
        "bookmaker": ["MockBet"] * len(df_games)
    })
    
    # Unpivot to have 'side' and 'odds'
    odds_long = odds_df.unpivot(
        index=["player_id", "season", "week", "market", "line", "bookmaker"],
        on=["odds_over", "odds_under"],
        variable_name="side",
        value_name="odds"
    )
    
    odds_long = odds_long.with_columns(
        pl.col("side").str.replace("odds_", "")
    )
    
    return odds_long
