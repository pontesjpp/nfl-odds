import nflreadpy as nfl
import polars as pl
import pandas as pd
from typing import List

def load_historical_pbp(years: List[int]) -> pl.DataFrame:
    """Load play-by-play data for the given years."""
    df = nfl.load_pbp(years)
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df)
    return df

def load_player_stats(years: List[int]) -> pl.DataFrame:
    """Load player-level weekly stats for the given years."""
    df = nfl.load_player_stats(years)
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df)
    return df

def load_rosters(years: List[int]) -> pl.DataFrame:
    """Load seasonal rosters to map player IDs."""
    df = nfl.load_roster_data(years)
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df)
    return df

def load_schedules(years: List[int]) -> pl.DataFrame:
    """Load game schedules including Vegas odds and weather."""
    df = nfl.load_schedules(years)
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df)
    return df

def load_snap_counts(years: List[int]) -> pl.DataFrame:
    """Load snap count data for players."""
    df = nfl.load_snap_counts(years)
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df)
    return df

def load_pfr_rush(years: List[int]) -> pl.DataFrame:
    df = nfl.load_pfr_advstats(years, stat_type='rush')
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df)
    return df

def load_ftn_charting(years: List[int]) -> pl.DataFrame:
    df = nfl.load_ftn_charting(years)
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df)
    return df

def load_injuries(years: List[int]) -> pl.DataFrame:
    df = nfl.load_injuries(years)
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df)
    return df

def load_depth_charts(years: List[int]) -> pl.DataFrame:
    df = nfl.load_depth_charts(years)
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df)
    return df

def load_player_ids() -> pl.DataFrame:
    df = nfl.load_ff_playerids()
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df)
    return df
