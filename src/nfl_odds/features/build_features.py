import polars as pl
from typing import List

def calculate_rolling_stats(df: pl.DataFrame, target_cols: List[str], window_sizes: List[int]) -> pl.DataFrame:
    """Calculate rolling averages for specified stats."""
    df = df.sort(["player_id", "season", "week"])
    exprs = []
    for col in target_cols:
        for w in window_sizes:
            exprs.append(
                pl.col(col).rolling_mean(window_size=w, min_periods=1).over("player_id").alias(f"{col}_avg_{w}")
            )
    
    return df.with_columns(exprs)

def _apply_shrinkage(df: pl.DataFrame, col: str, k: float) -> pl.DataFrame:
    """Applies bayesian shrinkage to a season_avg column based on positional mean."""
    pos_mean_col = f"{col}_pos_mean"
    if "position" in df.columns:
        pos_mean = df.group_by(["position", "season", "week"]).agg(
            pl.col(f"{col}_season_avg").mean().alias(pos_mean_col)
        )
        df = df.join(pos_mean, on=["position", "season", "week"], how="left")
        
        n = pl.col("games_played_sample_size")
        shrunk = (n / (n + k)) * pl.col(f"{col}_season_avg") + (k / (n + k)) * pl.col(pos_mean_col)
        df = df.with_columns(shrunk.fill_nan(0).alias(f"{col}_shrunk_season_avg"))
    
    return df

def build_player_features(
    df_player_stats: pl.DataFrame, 
    df_schedules: pl.DataFrame = None, 
    df_snaps: pl.DataFrame = None, 
    df_pbp: pl.DataFrame = None,
    df_pfr: pl.DataFrame = None,
    df_ftn: pl.DataFrame = None,
    df_inj: pl.DataFrame = None,
    df_dc: pl.DataFrame = None,
    df_ids: pl.DataFrame = None
) -> pl.DataFrame:
    """Build advanced features including usage, game environment, and defensive matchup."""
    
    target_stats = [
        "passing_yards", "attempts", "completions",
        "rushing_yards", "carries", 
        "receiving_yards", "receptions", "targets", "receiving_yards_after_catch",
        "passing_epa", "passing_cpoe", "sacks_suffered", "passing_air_yards",
        "wopr", "target_share", "air_yards_share", "receiving_air_yards"
    ]
    
    df = df_player_stats.sort(["player_id", "season", "week"])
    
    # 5.1 Sample size for shrinkage
    df = df.with_columns(
        pl.col("player_id").cum_count().over(["player_id", "season"]).shift(1).fill_null(0).alias("games_played_sample_size")
    )
    
    rolling_exprs = []
    for col in target_stats:
        for w in [3, 5, 10]:
            rolling_exprs.append(
                pl.col(col).shift(1).rolling_mean(window_size=w, min_periods=1).over("player_id").alias(f"{col}_avg_{w}")
            )
            # 5.3 Standardization: EWM
            if w in [3, 5]:
                rolling_exprs.append(
                    pl.col(col).shift(1).ewm_mean(span=w, min_periods=1).over("player_id").alias(f"{col}_ewm_{w}")
                )
        # 5.2 Variance
        rolling_exprs.append(
            pl.col(col).shift(1).rolling_std(window_size=5, min_periods=2).over("player_id").alias(f"{col}_std_5")
        )
            
    expanding_exprs = []
    for col in target_stats:
        expanding_exprs.append(
            pl.col(col).shift(1).cumulative_eval(pl.element().mean()).over(["player_id", "season"]).alias(f"{col}_season_avg")
        )
        # 5.2 Variance Season
        expanding_exprs.append(
            pl.col(col).shift(1).cumulative_eval(pl.element().std()).over(["player_id", "season"]).alias(f"{col}_std_season")
        )

    df = df.with_columns(rolling_exprs + expanding_exprs)
    
    df = df.with_columns([
        (pl.col("receptions_avg_3") / pl.col("targets_avg_3")).fill_nan(0.0).alias("catch_rate_avg_3"),
        (pl.col("receptions_avg_5") / pl.col("targets_avg_5")).fill_nan(0.0).alias("catch_rate_avg_5"),
        (pl.col("receptions_season_avg") / pl.col("targets_season_avg")).fill_nan(0.0).alias("catch_rate_season_avg"),
        (pl.col("passing_epa_avg_5") / (pl.col("attempts_avg_5") + pl.col("sacks_suffered_avg_5"))).fill_nan(0.0).alias("epa_per_dropback_avg_5"),
        (pl.col("passing_epa_season_avg") / (pl.col("attempts_season_avg") + pl.col("sacks_suffered_season_avg"))).fill_nan(0.0).alias("epa_per_dropback_season_avg"),
        (pl.col("sacks_suffered_avg_5") / (pl.col("attempts_avg_5") + pl.col("sacks_suffered_avg_5"))).fill_nan(0.0).alias("sack_rate_avg_5"),
        (pl.col("sacks_suffered_season_avg") / (pl.col("attempts_season_avg") + pl.col("sacks_suffered_season_avg"))).fill_nan(0.0).alias("sack_rate_season_avg"),
        (pl.col("passing_air_yards_avg_5") / pl.col("attempts_avg_5")).fill_nan(0.0).alias("adot_avg_5"),
        (pl.col("passing_air_yards_season_avg") / pl.col("attempts_season_avg")).fill_nan(0.0).alias("adot_season_avg"),
        (pl.col("receiving_air_yards_avg_5") / pl.col("targets_avg_5")).fill_nan(0.0).alias("receiving_adot_avg_5"),
        (pl.col("receiving_air_yards_season_avg") / pl.col("targets_season_avg")).fill_nan(0.0).alias("receiving_adot_season_avg"),
    ])
    
    # 4. Receiving: qb_epa_per_dropback_avg_5 (for the receiver's team)
    team_qb_epa = df.filter(pl.col("position") == "QB").group_by(["team", "season", "week"]).agg(
        pl.col("epa_per_dropback_avg_5").mean().alias("team_qb_epa_per_dropback_avg_5")
    )
    df = df.join(team_qb_epa, on=["team", "season", "week"], how="left")
    
    if df_snaps is not None and df_ids is not None:
        pfr_map = df_ids.select(["pfr_id", "gsis_id"]).drop_nulls().unique()
        df_snaps_j = df_snaps.join(pfr_map, left_on="pfr_player_id", right_on="pfr_id", how="left").rename({"gsis_id": "player_id"})
        df_snaps_sub = df_snaps_j.select(["player_id", "season", "week", "offense_pct"])
        df = df.join(df_snaps_sub, on=["player_id", "season", "week"], how="left")
        df = df.sort(["player_id", "season", "week"]).with_columns([
            pl.col("offense_pct").shift(1).rolling_mean(window_size=5, min_periods=1).over("player_id").alias("offense_pct_avg_5"),
            pl.col("offense_pct").shift(1).ewm_mean(span=3, min_periods=1).over("player_id").alias("offense_pct_ewm_3")
        ])
        
        # 5.2 Role stability score
        df = df.with_columns(
            (1.0 / (1.0 + pl.col("offense_pct").shift(1).rolling_std(window_size=3, min_periods=2).over("player_id").fill_null(1.0))).alias("role_stability_score")
        )
        
    if df_pbp is not None:
        # Red zone features
        rz_plays = df_pbp.filter((pl.col("yardline_100") <= 20) & (pl.col("pass_attempt") == 1))
        rz_targets = rz_plays.group_by(["receiver_player_id", "game_id"]).agg(
            pl.col("play_id").count().alias("red_zone_targets")
        ).rename({"receiver_player_id": "player_id"})
        df = df.join(rz_targets, on=["player_id", "game_id"], how="left").with_columns(pl.col("red_zone_targets").fill_null(0))
        
        rz_rush = df_pbp.filter((pl.col("yardline_100") <= 20) & (pl.col("rush_attempt") == 1))
        rz_carries = rz_rush.group_by(["rusher_player_id", "game_id"]).agg(
            pl.col("play_id").count().alias("red_zone_carries")
        ).rename({"rusher_player_id": "player_id"})
        df = df.join(rz_carries, on=["player_id", "game_id"], how="left").with_columns(pl.col("red_zone_carries").fill_null(0))
        
        df = df.sort(["player_id", "season", "week"]).with_columns([
            pl.col("red_zone_targets").shift(1).rolling_mean(window_size=5, min_periods=1).over("player_id").alias("red_zone_targets_avg_5"),
            pl.col("red_zone_carries").shift(1).ewm_mean(span=3, min_periods=1).over("player_id").alias("red_zone_carries_ewm_3")
        ])
        
        team_rz_carries = df.group_by(["team", "game_id"]).agg(pl.col("red_zone_carries").sum().alias("team_rz_carries"))
        df = df.join(team_rz_carries, on=["team", "game_id"], how="left")
        df = df.with_columns((pl.col("red_zone_carries") / pl.col("team_rz_carries")).fill_nan(0.0).alias("rz_carry_share"))
        df = df.sort(["player_id", "season", "week"]).with_columns([
            pl.col("rz_carry_share").shift(1).ewm_mean(span=3, min_periods=1).over("player_id").alias("rz_carry_share_ewm_3")
        ])
        
        # 4. Receiving: rz_efficiency_offense
        rz_tds = df_pbp.filter((pl.col("yardline_100") <= 20) & (pl.col("touchdown") == 1)).group_by(["posteam", "game_id", "season", "week"]).agg(pl.col("play_id").count().alias("rz_tds"))
        rz_trips = df_pbp.filter(pl.col("yardline_100") <= 20).group_by(["posteam", "game_id", "season", "week"]).agg(pl.col("series").n_unique().alias("rz_trips"))
        team_rz_eff = rz_tds.join(rz_trips, on=["posteam", "game_id", "season", "week"], how="outer").fill_null(0)
        team_rz_eff = team_rz_eff.with_columns((pl.col("rz_tds") / pl.col("rz_trips")).fill_nan(0.0).alias("rz_efficiency"))
        team_rz_eff = team_rz_eff.sort(["posteam", "season", "week"]).with_columns(
            pl.col("rz_efficiency").shift(1).rolling_mean(window_size=5, min_periods=1).over("posteam").alias("rz_efficiency_offense_avg_5")
        ).rename({"posteam": "team"})
        df = df.join(team_rz_eff.select(["team", "game_id", "rz_efficiency_offense_avg_5"]), on=["team", "game_id"], how="left")
        
        # 1. Pace and Game Script
        team_plays = df_pbp.filter(pl.col("play_type").is_in(["pass", "run"])).group_by(["posteam", "game_id", "season", "week"]).agg(pl.col("play_id").count().alias("team_plays"))
        team_plays = team_plays.sort(["posteam", "season", "week"]).with_columns(
            pl.col("team_plays").shift(1).rolling_mean(window_size=5, min_periods=1).over("posteam").alias("team_plays_per_game_avg_5")
        ).rename({"posteam": "team"})
        df = df.join(team_plays.select(["team", "game_id", "team_plays_per_game_avg_5"]), on=["team", "game_id"], how="left")
        
        opp_plays = df_pbp.filter(pl.col("play_type").is_in(["pass", "run"])).group_by(["defteam", "game_id", "season", "week"]).agg(pl.col("play_id").count().alias("opp_plays"))
        opp_plays = opp_plays.sort(["defteam", "season", "week"]).with_columns(
            pl.col("opp_plays").shift(1).rolling_mean(window_size=5, min_periods=1).over("defteam").alias("opp_plays_per_game_avg_5")
        ).rename({"defteam": "opponent_team"})
        df = df.join(opp_plays.select(["opponent_team", "game_id", "opp_plays_per_game_avg_5"]), on=["opponent_team", "game_id"], how="left")
        
        if "pass_oe" in df_pbp.columns:
            team_proe = df_pbp.filter(pl.col("pass_oe").is_not_null()).group_by(["posteam", "game_id", "season", "week"]).agg(pl.col("pass_oe").mean().alias("proe"))
            team_proe = team_proe.sort(["posteam", "season", "week"]).with_columns([
                pl.col("proe").shift(1).rolling_mean(window_size=5, min_periods=1).over("posteam").alias("proe_avg_5"),
                pl.col("proe").shift(1).cumulative_eval(pl.element().mean()).over(["posteam", "season"]).alias("proe_season_avg")
            ]).rename({"posteam": "team"})
            df = df.join(team_proe.select(["team", "game_id", "proe_avg_5", "proe_season_avg"]), on=["team", "game_id"], how="left")
        else:
            df = df.with_columns([pl.lit(0.0).alias("proe_avg_5"), pl.lit(0.0).alias("proe_season_avg")])
            
        if "wp" in df_pbp.columns:
            neutral_plays = df_pbp.filter((pl.col("wp") >= 0.2) & (pl.col("wp") <= 0.8) & pl.col("play_type").is_in(["pass", "run"]))
            team_neutral = neutral_plays.group_by(["posteam", "game_id", "season", "week"]).agg(pl.col("pass_attempt").mean().alias("neutral_pass_rate"))
            team_neutral = team_neutral.sort(["posteam", "season", "week"]).with_columns(
                pl.col("neutral_pass_rate").shift(1).rolling_mean(window_size=5, min_periods=1).over("posteam").alias("neutral_script_pass_rate_avg_5")
            ).rename({"posteam": "team"})
            df = df.join(team_neutral.select(["team", "game_id", "neutral_script_pass_rate_avg_5"]), on=["team", "game_id"], how="left")
        else:
            df = df.with_columns(pl.lit(0.0).alias("neutral_script_pass_rate_avg_5"))
            
        # 3. Rushing: def_run_stop_rate_avg_5
        run_stops = df_pbp.filter(pl.col("rush_attempt") == 1).with_columns((pl.col("yards_gained") <= 2).cast(pl.Float64).alias("is_run_stop"))
        def_run_stops = run_stops.group_by(["defteam", "game_id", "season", "week"]).agg(pl.col("is_run_stop").mean().alias("run_stop_rate"))
        def_run_stops = def_run_stops.sort(["defteam", "season", "week"]).with_columns(
            pl.col("run_stop_rate").shift(1).rolling_mean(window_size=5, min_periods=1).over("defteam").alias("def_run_stop_rate_avg_5")
        ).rename({"defteam": "opponent_team"})
        df = df.join(def_run_stops.select(["opponent_team", "game_id", "def_run_stop_rate_avg_5"]), on=["opponent_team", "game_id"], how="left")
    
    team_carries = df.group_by(["team", "game_id"]).agg(pl.col("carries").sum().alias("team_total_carries"))
    df = df.join(team_carries, on=["team", "game_id"], how="left")
    df = df.with_columns((pl.col("carries") / pl.col("team_total_carries")).fill_nan(0.0).alias("carry_share"))
    df = df.sort(["player_id", "season", "week"]).with_columns([
         pl.col("carry_share").shift(1).ewm_mean(span=3, min_periods=1).over("player_id").alias("carry_share_ewm_3"),
         pl.col("carry_share").shift(1).cumulative_eval(pl.element().mean()).over(["player_id", "season"]).alias("carry_share_season_avg")
    ])

    # 3. Rushing: Committee entropy
    if "carry_share" in df.columns:
        # Entropy = -sum(p * log(p))
        entropy_df = df.filter(pl.col("carry_share") > 0).with_columns(
            (pl.col("carry_share") * pl.col("carry_share").log()).alias("p_log_p")
        )
        team_entropy = entropy_df.group_by(["team", "game_id", "season", "week"]).agg(
            (-pl.col("p_log_p").sum()).alias("committee_entropy_game")
        )
        team_entropy = team_entropy.sort(["team", "season", "week"]).with_columns(
            pl.col("committee_entropy_game").shift(1).rolling_mean(window_size=3, min_periods=1).over("team").alias("committee_entropy_avg_3")
        )
        df = df.join(team_entropy.select(["team", "game_id", "committee_entropy_avg_3"]), on=["team", "game_id"], how="left")

    if df_pfr is not None and df_ids is not None:
        pfr_map = df_ids.select(["pfr_id", "gsis_id"]).drop_nulls().unique()
        df_pfr_j = df_pfr.join(pfr_map, left_on="pfr_player_id", right_on="pfr_id", how="left").rename({"gsis_id": "player_id"})
        df_pfr_select = df_pfr_j.select(["player_id", "season", "week", "rushing_yards_before_contact", "rushing_yards_after_contact"]).unique(subset=["player_id", "season", "week"])
        df = df.join(df_pfr_select, on=["player_id", "season", "week"], how="left")
        df = df.sort(["player_id", "season", "week"]).with_columns([
            pl.col("rushing_yards_before_contact").shift(1).rolling_mean(window_size=3, min_periods=1).over("player_id").alias("rybc_avg_3"),
            pl.col("rushing_yards_after_contact").shift(1).rolling_mean(window_size=3, min_periods=1).over("player_id").alias("ryac_avg_3"),
            pl.col("rushing_yards_before_contact").shift(1).ewm_mean(span=3, min_periods=1).over("player_id").alias("rybc_ewm_3"),
            pl.col("rushing_yards_after_contact").shift(1).ewm_mean(span=3, min_periods=1).over("player_id").alias("ryac_ewm_3")
        ])

    if df_ftn is not None and df_pbp is not None:
        pbp_rush = df_pbp.filter(pl.col("rush_attempt") == 1).select(["game_id", "play_id", "rusher_player_id"]).drop_nulls()
        ftn_box = df_ftn.select(["nflverse_game_id", "nflverse_play_id", "n_defense_box"]).drop_nulls().with_columns(pl.col("nflverse_play_id").cast(pl.Float64))
        box_data = pbp_rush.join(ftn_box, left_on=["game_id", "play_id"], right_on=["nflverse_game_id", "nflverse_play_id"], how="inner")
        box_data = box_data.with_columns((pl.col("n_defense_box") <= 6).cast(pl.Float64).alias("is_light_box"))
        box_agg = box_data.group_by(["game_id", "rusher_player_id"]).agg([
            pl.col("is_light_box").mean().alias("light_box_pct"),
            pl.col("n_defense_box").mean().alias("avg_box_count")
        ]).rename({"rusher_player_id": "player_id"})
        df = df.join(box_agg, on=["game_id", "player_id"], how="left")
        df = df.sort(["player_id", "season", "week"]).with_columns([
            pl.col("light_box_pct").shift(1).rolling_mean(window_size=3, min_periods=1).over("player_id").alias("light_box_pct_avg_3"),
            pl.col("avg_box_count").shift(1).rolling_mean(window_size=3, min_periods=1).over("player_id").alias("avg_box_count_avg_3")
        ])

    df_def = df_player_stats.group_by(["opponent_team", "season", "week", "game_id"]).agg([
        pl.col("passing_yards").sum().alias("def_pass_yds_allowed"),
        pl.col("rushing_yards").sum().alias("def_rush_yds_allowed")
    ]).sort(["opponent_team", "season", "week"])
    
    if df_pbp is not None:
        pbp_def = df_pbp.filter(pl.col("rush_attempt") == 1).group_by(["defteam", "season", "week"]).agg([
            pl.col("epa").mean().alias("def_rush_epa_per_att")
        ]).rename({"defteam": "opponent_team"})
        df_def = df_def.join(pbp_def, on=["opponent_team", "season", "week"], how="left")
        
        # 2. Passing: def_pass_epa_allowed_avg_5
        pbp_pass_def = df_pbp.filter(pl.col("pass_attempt") == 1).group_by(["defteam", "season", "week"]).agg([
            pl.col("epa").mean().alias("def_pass_epa_per_dropback")
        ]).rename({"defteam": "opponent_team"})
        df_def = df_def.join(pbp_pass_def, on=["opponent_team", "season", "week"], how="left")

        # 2. Passing: def_pressure_rate_generated_avg_5
        # NOTE: This is a simulated proxy (qb_hit + sack limited to 1), not true pressure rate.
        # It likely underestimates actual pressure since it doesn't capture hurries without a hit/sack.
        # If charting data (PFF/NextGen) becomes available, replace this.
        pbp_press_def = df_pbp.filter(pl.col("pass_attempt") == 1).with_columns(
            (pl.col("qb_hit") + pl.col("sack")).clip(0, 1).alias("pressure")
        ).group_by(["defteam", "season", "week"]).agg([
            pl.col("pressure").mean().alias("def_pressure_rate_generated")
        ]).rename({"defteam": "opponent_team"})
        df_def = df_def.join(pbp_press_def, on=["opponent_team", "season", "week"], how="left")

    # Pre-calculate previous season full-season averages for each defense (for Week 1 baseline)
    prev_season_def = df_def.group_by(["opponent_team", "season"]).agg([
        pl.col("def_pass_yds_allowed").mean().alias("prev_def_pass_yds_allowed_season_avg"),
        pl.col("def_rush_yds_allowed").mean().alias("prev_def_rush_yds_allowed_season_avg")
    ]).with_columns(
        (pl.col("season") + 1).alias("season")
    )
    df_def = df_def.join(prev_season_def, on=["opponent_team", "season"], how="left")

    df_def_cols = [
        pl.col("def_pass_yds_allowed").shift(1).rolling_mean(window_size=5, min_periods=1).over("opponent_team").alias("def_pass_yds_allowed_avg_5"),
        pl.col("def_rush_yds_allowed").shift(1).rolling_mean(window_size=5, min_periods=1).over("opponent_team").alias("def_rush_yds_allowed_avg_5"),
        pl.when(pl.col("week") == 1)
          .then(pl.col("prev_def_pass_yds_allowed_season_avg"))
          .otherwise(pl.col("def_pass_yds_allowed").shift(1).cumulative_eval(pl.element().mean()).over(["opponent_team", "season"]))
          .alias("def_pass_yds_allowed_season_avg"),
        pl.when(pl.col("week") == 1)
          .then(pl.col("prev_def_rush_yds_allowed_season_avg"))
          .otherwise(pl.col("def_rush_yds_allowed").shift(1).cumulative_eval(pl.element().mean()).over(["opponent_team", "season"]))
          .alias("def_rush_yds_allowed_season_avg")
    ]
    if df_pbp is not None:
        df_def_cols.append(pl.col("def_rush_epa_per_att").shift(1).rolling_mean(window_size=5, min_periods=1).over("opponent_team").alias("def_rush_epa_avg_5"))
        df_def_cols.append(pl.col("def_pass_epa_per_dropback").shift(1).rolling_mean(window_size=5, min_periods=1).over("opponent_team").alias("def_pass_epa_allowed_avg_5"))
        df_def_cols.append(pl.col("def_pressure_rate_generated").shift(1).rolling_mean(window_size=5, min_periods=1).over("opponent_team").alias("def_pressure_rate_generated_avg_5"))
        
        # 2 & 3. Adjusted EPAs (Proxy: just using the raw epa since full ridge regression is complex)
        df_def_cols.append(pl.col("def_rush_epa_per_att").shift(1).rolling_mean(window_size=5, min_periods=1).over("opponent_team").alias("def_rush_epa_avg_5_UNADJUSTED_STUB"))
        df_def_cols.append(pl.col("def_pass_epa_per_dropback").shift(1).rolling_mean(window_size=5, min_periods=1).over("opponent_team").alias("def_pass_epa_allowed_avg_5_UNADJUSTED_STUB"))
        
    df_def = df_def.with_columns(df_def_cols)
    
    select_cols = [
        "game_id", "opponent_team", 
        "def_pass_yds_allowed_avg_5", "def_rush_yds_allowed_avg_5",
        "def_pass_yds_allowed_season_avg", "def_rush_yds_allowed_season_avg"
    ]
    if df_pbp is not None:
        select_cols.extend(["def_rush_epa_avg_5", "def_pass_epa_allowed_avg_5", "def_pressure_rate_generated_avg_5", "def_rush_epa_avg_5_UNADJUSTED_STUB", "def_pass_epa_allowed_avg_5_UNADJUSTED_STUB"])
        
    df = df.join(df_def.select(select_cols), on=["game_id", "opponent_team"], how="left")
    
    if df_schedules is not None:
        # Include total_line, spread_line, rest, surface, wind, temp
        df_env = df_schedules.select([
            "game_id", "home_team", "away_team", "total_line", "spread_line", "wind", "temp", "home_spread_odds", "surface", "home_rest", "away_rest"
        ])
        df = df.join(df_env, on="game_id", how="left")
        
        df = df.with_columns([
            pl.when(pl.col("team") == pl.col("home_team")).then(True).otherwise(False).alias("is_home")
        ])
        
        df = df.with_columns([
            pl.when(pl.col("is_home")).then(pl.col("spread_line"))
              .otherwise(-pl.col("spread_line")).alias("implied_spread"),
            pl.when(pl.col("is_home")).then(pl.col("total_line") / 2 + pl.col("spread_line") / 2)
              .otherwise(pl.col("total_line") / 2 - pl.col("spread_line") / 2).alias("implied_team_total"),
            pl.when(pl.col("is_home")).then(pl.col("home_rest")).otherwise(pl.col("away_rest")).alias("days_rest")
        ])
        
        df = df.with_columns([
            pl.col("surface").str.to_lowercase().str.contains("turf|astroturf|fieldturf").alias("is_turf").cast(pl.Float64).fill_null(0.0),
            (pl.col("days_rest") < 6).cast(pl.Float64).alias("is_short_week"),
            pl.col("temp").alias("weather_temp"),
            pl.lit(0.0).alias("precipitation_pct") # Placeholder since it's not in df_sched
        ])
        
        # 1. Pace and Game Script: line movements
        df = df.with_columns([
            pl.lit(None).alias("line_movement_total"),
            pl.lit(None).alias("line_movement_spread")
        ])
        
    # INJURY DATA (Starting QB out, Backup RB injury status, qb_injury_designation)
    # Using df_inj and df_dc
    df = df.with_columns([
        pl.lit(None).alias("starting_qb_out"),
        pl.lit(None).alias("backup_rb_injury_status"),
        pl.lit(None).alias("qb_injury_designation"),
        pl.lit(None).alias("games_since_return_from_injury"),
        pl.lit(None).alias("route_participation_rate_avg_5"),
        pl.lit(None).alias("teammate_injury_redistribution_elasticity"),
        pl.lit(None).alias("slot_vs_outside_coverage_grade_allowed"),
        pl.lit(None).alias("shadow_coverage_flag"),
        pl.lit(None).alias("wr_corps_epa_per_target_weighted")
    ])
        
    # Shrinkage
    for c in ["passing_yards", "rushing_yards", "receiving_yards", "target_share", "carry_share", "wopr"]:
        if f"{c}_season_avg" in df.columns:
            # calibration constant k determined via backtest
            k = 2.0
            df = _apply_shrinkage(df, c, k)

    # 2. Passing Interactions
    df = df.with_columns([
        (pl.col("implied_team_total") * pl.col("proe_avg_5")).fill_null(0.0).alias("implied_team_total_x_proe"),
        (pl.col("sack_rate_avg_5") * pl.col("def_pressure_rate_generated_avg_5")).fill_null(0.0).alias("sack_rate_x_def_pressure")
    ])
    
    # 3. Rushing Interactions
    df = df.with_columns([
        (pl.col("light_box_pct_avg_3") * pl.col("def_rush_epa_avg_5")).fill_null(0.0).alias("light_box_x_def_rush_epa"),
        (pl.col("implied_spread") * pl.col("rz_carry_share_ewm_3")).fill_null(0.0).alias("implied_spread_x_rz_carry_share"),
        (pl.col("carry_share_ewm_3") * pl.col("backup_rb_injury_status")).fill_null(0.0).alias("carry_share_x_backup_injury")
    ])
    
    # 4. Receiving Interactions
    df = df.with_columns([
        (pl.col("wopr_avg_5") * pl.col("implied_team_total")).fill_null(0.0).alias("wopr_x_implied_total"),
        (pl.col("target_share_avg_5") * pl.col("teammate_injury_redistribution_elasticity")).fill_null(0.0).alias("target_share_x_redistribution"),
        (pl.col("red_zone_targets_avg_5") * pl.col("rz_efficiency_offense_avg_5")).fill_null(0.0).alias("rz_targets_x_rz_efficiency")
    ])

    new_features = [
        "rybc_avg_3", "ryac_avg_3", 
        "light_box_pct_avg_3", "avg_box_count_avg_3", 
        "def_rush_epa_avg_5", 
        "offense_pct_ewm_3", "rz_carry_share_ewm_3", "carry_share_ewm_3", 
        "implied_spread"
    ]
    df = df.with_columns([
        pl.col(col).fill_null(0.0) for col in new_features if col in df.columns
    ])
        
    
    if df_ids is not None:
        espn_map = df_ids.select(["gsis_id", "espn_id"]).drop_nulls().unique()
        df = df.join(espn_map, left_on="player_id", right_on="gsis_id", how="left")
        
    return df
