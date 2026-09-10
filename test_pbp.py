import nflreadpy as nfl
import polars as pl
try:
    df_pbp = nfl.load_pbp([2024])
    cols = df_pbp.columns
    print([c for c in cols if 'contact' in c.lower() or 'epa' in c.lower() or 'rush' in c.lower()])
except Exception as e:
    print(f"Error PBP: {e}")
