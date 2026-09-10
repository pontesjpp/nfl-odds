import polars as pl
from nfl_odds.data.collect_nfl import load_player_stats, load_schedules
from nfl_odds.features.build_features import build_player_features

df_stats = load_player_stats([2024])
df_sched = load_schedules([2024])
df_features = build_player_features(df_stats, df_sched)

print("Features columns:", df_features.columns)
print("Some names:", df_features.select("player_name").head(10))
if "player_display_name" in df_features.columns:
    print("Display names:", df_features.select("player_display_name").head(10))
