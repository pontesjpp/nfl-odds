import nflreadpy as nfl
try:
    df_dc = nfl.load_depth_charts([2024])
    print(df_dc.columns)
except Exception as e:
    print(f"Error DC: {e}")
