import nflreadpy as nfl
import polars as pl
from datetime import datetime, timedelta
import os

def get_upcoming_games(season=2026, week=None):
    """
    Fetches the schedule using nflreadpy.
    """
    schedules = nfl.load_schedules([season])
    
    # Convert to polars
    if not isinstance(schedules, pl.DataFrame):
        import pandas as pd
        if isinstance(schedules, pd.DataFrame):
            df_sched = pl.from_pandas(schedules)
        else:
            raise ValueError("Unexpected type from nflreadpy")
    else:
        df_sched = schedules
            
    # Filter upcoming games
    now = datetime.now()
    
    # gameday is usually string like '2026-09-08'
    # gametime is like '13:00'
    
    # Simple logic for this week
    if week is None:
        # Get the current week based on the dates
        # This is simplified; ideally you map the current date to an NFL week
        df_upcoming = df_sched.filter(
            pl.col("gameday").str.strptime(pl.Date, "%Y-%m-%d") >= now.date()
        )
        if len(df_upcoming) > 0:
            week = df_upcoming["week"].min()
        else:
            week = 1
            
    df_week = df_sched.filter(pl.col("week") == week)
    
    return df_week.select(["game_id", "week", "away_team", "home_team", "gameday", "gametime", "spread_line", "total_line"])

if __name__ == "__main__":
    df = get_upcoming_games(season=2026, week=1)
    os.makedirs("data", exist_ok=True)
    df.write_parquet("data/upcoming_schedule.parquet")
    print(df.head())
