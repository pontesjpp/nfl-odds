import numpy as np
import polars as pl

def calculate_implied_probability(odds: float) -> float:
    return 1.0 / odds if odds > 0 else 0.0

def calculate_ev(model_prob_win: float, odds: float, stake: float = 10.0) -> float:
    profit_if_win = (odds - 1.0) * stake
    prob_loss = 1.0 - model_prob_win
    return (model_prob_win * profit_if_win) - (prob_loss * stake)

def calculate_edge(model_prob_win: float, implied_prob: float) -> float:
    return model_prob_win - implied_prob

def analyze_opportunities(df_odds: pl.DataFrame, model_probs: np.ndarray) -> pl.DataFrame:
    """
    df_odds must have columns: ['odds', 'side', 'line']
    model_probs is the probability of OVER.
    """
    
    # Calculate prob of winning depending on the side
    # If side is 'over', prob_win = model_probs
    # If side is 'under', prob_win = 1.0 - model_probs
    
    probs = pl.Series("model_prob", model_probs)
    df = df_odds.with_columns(probs)
    
    df = df.with_columns(
        pl.when(pl.col("side") == "over").then(pl.col("model_prob"))
        .otherwise(1.0 - pl.col("model_prob")).alias("prob_win")
    )
    
    df = df.with_columns([
        (1.0 / pl.col("odds")).alias("implied_prob")
    ])
    
    df = df.with_columns([
        (pl.col("prob_win") - pl.col("implied_prob")).alias("edge"),
        (pl.col("prob_win") * (pl.col("odds") - 1.0) * 10.0 - (1.0 - pl.col("prob_win")) * 10.0).alias("ev_10_eur")
    ])
    
    df = df.with_columns([
        ((pl.col("ev_10_eur") / 10.0) * 100.0).alias("ev_percent"),
        (1.0 / pl.col("prob_win")).alias("fair_odds")
    ])
    
    return df
