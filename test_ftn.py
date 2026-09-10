import nflreadpy as nfl
import polars as pl
try:
    df_ftn = nfl.load_ftn_charting([2024])
    print(df_ftn.columns)
except Exception as e:
    print(f"Error FTN: {e}")
