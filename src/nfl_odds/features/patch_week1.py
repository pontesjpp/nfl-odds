import os
import polars as pl
from nfl_odds.data.collect_nfl import load_player_ids, load_player_stats

TEAM_MAP = {
    "GBP": "GB", "SFO": "SF", "LAR": "LA", "KCC": "KC",
    "TBB": "TB", "NEP": "NE", "NOS": "NO", "LVR": "LV",
    "JAC": "JAX", "OAK": "LV", "SDC": "LAC", "STL": "LA", "RAM": "LA"
}

def patch_week1_teams(df_test_base: pl.DataFrame) -> pl.DataFrame:
    """
    Overwrites the 'team' and team/opponent features in the latest player row 
    based on the 2026 depth charts / df_ids for Week 1 Cold Start.
    """
    df_ids = load_player_ids()
    # df_ids has 'gsis_id' and 'team'
    team_map = df_ids.select(["gsis_id", "team"]).drop_nulls()
    team_map = team_map.rename({"gsis_id": "player_id", "team": "current_team"})
    team_map = team_map.with_columns(pl.col("current_team").replace(TEAM_MAP))
    
    # Also augment with 2026 depth chart teams for any traded/free agent players
    try:
        dc_path = "data/depth_charts_2026_2027/nfl_offensive_depth_charts_2026_2027.csv"
        if os.path.exists(dc_path):
            df_dc = pl.read_csv(dc_path)
            if "espn_id" in df_dc.columns and "team" in df_dc.columns:
                dc_team = df_dc.select(["espn_id", "team"]).drop_nulls().unique()
                dc_team = dc_team.rename({"team": "dc_team"})
                df_ids_espn = df_ids.select(["gsis_id", "espn_id"]).drop_nulls()
                dc_map = df_ids_espn.join(dc_team, on="espn_id", how="inner").rename({"gsis_id": "player_id"})
                team_map = team_map.join(dc_map.select(["player_id", "dc_team"]), on="player_id", how="left")
                team_map = team_map.with_columns(
                    pl.when(pl.col("dc_team").is_not_null())
                      .then(pl.col("dc_team"))
                      .otherwise(pl.col("current_team"))
                      .alias("current_team")
                ).drop("dc_team")
    except Exception as e:
        print(f"Warning: could not augment with 2026 depth chart team: {e}")
    
    # We also need the current opponent and vegas lines.
    try:
        from nfl_odds.odds.schedule_manager import get_upcoming_games
        df_sched = get_upcoming_games(2026, 1)
        # Create a mapping of team -> opponent & lines
        opp_map = []
        for row in df_sched.iter_rows(named=True):
            spread = row.get("spread_line", 0)
            total = row.get("total_line", 45)
            opp_map.append({"current_team": row["home_team"], "current_opponent": row["away_team"], "current_is_home": True, "current_spread_line": spread, "current_total_line": total})
            opp_map.append({"current_team": row["away_team"], "current_opponent": row["home_team"], "current_is_home": False, "current_spread_line": spread, "current_total_line": total})
        df_opp = pl.DataFrame(opp_map)
        team_map = team_map.join(df_opp, on="current_team", how="left")
    except Exception as e:
        print(f"Could not load upcoming schedule for opponent patching: {e}")
        team_map = team_map.with_columns([
            pl.lit(None).alias("current_opponent"),
            pl.lit(None).alias("current_is_home"),
            pl.lit(None).alias("current_spread_line"),
            pl.lit(None).alias("current_total_line")
        ])
        
    df = df_test_base.join(team_map, on="player_id", how="left")
    
    # Identify which rows are the LATEST for each player
    latest_rows = df.group_by("player_id").agg(pl.col("week").max())
    
    # Left join to identify if this is the latest row
    latest_rows = latest_rows.with_columns(pl.lit(True).alias("is_latest"))
    df = df.join(latest_rows, on=["player_id", "week"], how="left")
    df = df.with_columns(pl.col("is_latest").fill_null(False))
    
    # Overwrite 'team' and 'opponent_team' if is_latest and current_team is not null
    df = df.with_columns([
        pl.when(pl.col("is_latest") & pl.col("current_team").is_not_null())
          .then(pl.col("current_team"))
          .otherwise(pl.col("team"))
          .alias("team"),
          
        pl.when(pl.col("is_latest") & pl.col("current_opponent").is_not_null())
          .then(pl.col("current_opponent"))
          .otherwise(pl.col("opponent_team"))
          .alias("opponent_team"),
          
        pl.when(pl.col("is_latest") & pl.col("current_is_home").is_not_null())
          .then(pl.col("current_is_home"))
          .otherwise(pl.col("is_home"))
          .alias("is_home"),
          
        pl.when(pl.col("is_latest") & pl.col("current_spread_line").is_not_null())
          .then(pl.col("current_spread_line"))
          .otherwise(pl.col("spread_line"))
          .alias("spread_line"),
          
        pl.when(pl.col("is_latest") & pl.col("current_total_line").is_not_null())
          .then(pl.col("current_total_line"))
          .otherwise(pl.col("total_line"))
          .alias("total_line")
    ])
    
    # Recalculate implied totals based on the newly patched Vegas lines!
    df = df.with_columns([
        pl.when(pl.col("is_home")).then(pl.col("spread_line"))
          .otherwise(-pl.col("spread_line")).alias("implied_spread"),
        pl.when(pl.col("is_home")).then(pl.col("total_line") / 2 + pl.col("spread_line") / 2)
          .otherwise(pl.col("total_line") / 2 - pl.col("spread_line") / 2).alias("implied_team_total")
    ])
    
    # NOW we must re-join the team and opponent features!
    team_cols = [
        "team_plays_per_game_avg_5", "proe_avg_5", "neutral_script_pass_rate_avg_5", 
        "team_qb_epa_per_dropback_avg_5", "committee_entropy_avg_3",
        "rz_efficiency_offense_avg_5"
    ]
    opp_cols = [
        "def_rush_yds_allowed_avg_5", "def_rush_yds_allowed_season_avg",
        "def_pass_yds_allowed_avg_5", "def_pass_yds_allowed_season_avg",
        "def_rush_epa_avg_5", "def_run_stop_rate_avg_5",
        "def_pass_epa_allowed_avg_5", "def_pressure_rate_allowed_avg_5",
        "opp_plays_per_game_avg_5", "def_pressure_rate_generated_avg_5"
    ]
    
    # Ensure chronological order by week so rolling stats take the end of the previous season
    df_sorted = df_test_base.sort(["week"])

    # Get the latest stats for each TEAM from 2025
    latest_team_stats = df_sorted.group_by("team").agg([
        pl.col(c).drop_nulls().last() for c in team_cols if c in df_test_base.columns
    ])
    
    latest_opp_stats = df_sorted.group_by("opponent_team").agg([
        pl.col(c).drop_nulls().last() for c in opp_cols if c in df_test_base.columns
    ])

    # For Week 1 baseline, use the full season average from the previous season (2025)
    try:
        df_stats_prev = load_player_stats([2025])
        df_def_prev = df_stats_prev.group_by(["opponent_team", "game_id"]).agg([
            pl.col("rushing_yards").sum().alias("def_rush_yds"),
            pl.col("passing_yards").sum().alias("def_pass_yds"),
        ]).group_by("opponent_team").agg([
            pl.col("def_rush_yds").mean().alias("def_rush_yds_allowed_season_avg"),
            pl.col("def_pass_yds").mean().alias("def_pass_yds_allowed_season_avg"),
        ])
        latest_opp_stats = latest_opp_stats.drop(["def_rush_yds_allowed_season_avg", "def_pass_yds_allowed_season_avg"], strict=False)
        latest_opp_stats = latest_opp_stats.join(df_def_prev, on="opponent_team", how="left")
    except Exception as e:
        print(f"Warning: Could not calculate full season previous defense averages: {e}")
    
    # Overwrite the features in the dataframe using the NEW team and opponent!
    df = df.drop(team_cols, strict=False).drop(opp_cols, strict=False)
    
    df = df.join(latest_team_stats, on="team", how="left")
    df = df.join(latest_opp_stats, on="opponent_team", how="left")

    # Safe fallbacks for team and opponent features to guarantee no nulls
    for c in team_cols:
        if c in df.columns:
            m_val = df_sorted[c].drop_nulls().mean() if c in df_sorted.columns else 0.0
            if m_val is None:
                m_val = 0.0
            df = df.with_columns(pl.col(c).fill_null(float(m_val)))
    for c in opp_cols:
        if c in df.columns:
            m_val = df_sorted[c].drop_nulls().mean() if c in df_sorted.columns else 0.0
            if m_val is None:
                m_val = 0.0
            df = df.with_columns(pl.col(c).fill_null(float(m_val)))
    
    # Fill weather and environmental defaults for domes / missing conditions
    weather_cols = []
    if "weather_temp" in df.columns:
        weather_cols.append(pl.col("weather_temp").fill_null(70.0))
    else:
        weather_cols.append(pl.lit(70.0).alias("weather_temp"))
    if "wind" in df.columns:
        weather_cols.append(pl.col("wind").fill_null(0.0))
    else:
        weather_cols.append(pl.lit(0.0).alias("wind"))
    if "precipitation_pct" in df.columns:
        weather_cols.append(pl.col("precipitation_pct").fill_null(0.0))
    else:
        weather_cols.append(pl.lit(0.0).alias("precipitation_pct"))
    df = df.with_columns(weather_cols)

    # Recalculate interactions
    interaction_exprs = [
        (pl.col("implied_team_total") * pl.col("proe_avg_5")).fill_null(0.0).alias("implied_team_total_x_proe"),
        (pl.col("wopr_avg_5") * pl.col("implied_team_total")).fill_null(0.0).alias("wopr_x_implied_total")
    ]
    if "red_zone_targets_avg_5" in df.columns and "rz_efficiency_offense_avg_5" in df.columns:
        interaction_exprs.append(
            (pl.col("red_zone_targets_avg_5") * pl.col("rz_efficiency_offense_avg_5")).fill_null(0.0).alias("rz_targets_x_rz_efficiency")
        )
    if "target_share_avg_5" in df.columns and "teammate_injury_redistribution_elasticity" in df.columns:
        interaction_exprs.append(
            (pl.col("target_share_avg_5") * pl.col("teammate_injury_redistribution_elasticity")).fill_null(0.0).alias("target_share_x_redistribution")
        )
    if "light_box_pct_avg_3" in df.columns and "def_rush_epa_avg_5" in df.columns:
        interaction_exprs.append(
            (pl.col("light_box_pct_avg_3") * pl.col("def_rush_epa_avg_5")).fill_null(0.0).alias("light_box_x_def_rush_epa")
        )
    if "implied_spread" in df.columns and "rz_carry_share_ewm_3" in df.columns:
        interaction_exprs.append(
            (pl.col("implied_spread") * pl.col("rz_carry_share_ewm_3")).fill_null(0.0).alias("implied_spread_x_rz_carry_share")
        )
    if "carry_share_ewm_3" in df.columns and "backup_rb_injury_status" in df.columns:
        interaction_exprs.append(
            (pl.col("carry_share_ewm_3") * pl.col("backup_rb_injury_status")).fill_null(0.0).alias("carry_share_x_backup_injury")
        )
    if "sack_rate_avg_5" in df.columns and "def_pressure_rate_generated_avg_5" in df.columns:
        interaction_exprs.append(
            (pl.col("sack_rate_avg_5") * pl.col("def_pressure_rate_generated_avg_5")).fill_null(0.0).alias("sack_rate_x_def_pressure")
        )

    df = df.with_columns(interaction_exprs)
    
    # Drop temp columns (preserving is_latest for pipeline evaluation)
    df = df.drop(["current_team", "current_opponent", "current_is_home", "current_spread_line", "current_total_line"], strict=False)
    
    return df


