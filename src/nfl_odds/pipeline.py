import polars as pl
import os
import argparse
import asyncio
from nfl_odds.data.collect_nfl import (
    load_player_stats, load_schedules, load_historical_pbp, 
    load_snap_counts, load_pfr_rush, load_ftn_charting, 
    load_injuries, load_depth_charts, load_player_ids
)
from nfl_odds.features.build_features import build_player_features
from nfl_odds.features.patch_week1 import patch_week1_teams
from nfl_odds.models.train import PlayerPropModel, split_temporal
from nfl_odds.betting.ev_calc import analyze_opportunities

def run_pipeline(live=False):
    print("1. Collecting NFL Data (2022-2026)...")
    years_to_load = [2022, 2023, 2024, 2025, 2026]
    
    try:
        df_stats = load_player_stats(years_to_load)
    except Exception as e:
        print(f"Warning: Could not load 2026 stats ({e}). Falling back to 2022-2025.")
        years_to_load = [2022, 2023, 2024, 2025]
        df_stats = load_player_stats(years_to_load)
        
    df_sched = load_schedules(years_to_load + [2026] if 2026 not in years_to_load else years_to_load)
    df_snaps = load_snap_counts(years_to_load)
    df_pbp = load_historical_pbp(years_to_load)
    print("Loading additional advanced stats...")
    df_pfr = load_pfr_rush(years_to_load)
    df_ftn = load_ftn_charting(years_to_load)
    df_inj = load_injuries(years_to_load)
    df_dc = load_depth_charts(years_to_load)
    df_ids = load_player_ids()
    
    print("2. Building Features...")
    df_features = build_player_features(
        df_stats, df_sched, df_snaps, df_pbp, 
        df_pfr, df_ftn, df_inj, df_dc, df_ids
    )
    
    latest_season = df_features["season"].max()
    print(f"-> Latest season available in features: {latest_season}")
    
    print(f"3. Generating or Fetching Odds for {latest_season} season...")
    df_test_base = df_features.filter(pl.col("season") == latest_season)
    
    if live:
        print(f"-> USING REAL LINES FROM SCRAPER / PARQUET")
        df_odds = pl.read_parquet("data/betclic_parsed_odds.parquet")
        
        mapping_df = df_test_base.select(["player_id", "player_display_name"]).drop_nulls().unique()
        mapping_df = mapping_df.with_columns(pl.col("player_display_name").str.to_lowercase().alias("name_lower"))
        
        df_odds = df_odds.with_columns(pl.col("player_name").str.to_lowercase().alias("name_lower"))
        
        df_odds = df_odds.join(
            mapping_df, 
            on="name_lower", 
            how="inner"
        )
        
        latest_week_df = df_test_base.group_by("player_id").agg(pl.col("week").max())
        df_odds = df_odds.join(latest_week_df, on="player_id", how="inner")
        df_odds = df_odds.with_columns(pl.lit(latest_season).alias("season"))
    else:
        print("-> Run with --live to use real odds!")
        return
        
    print(f"4. Training XGBoost Models & Predicting for all markets...")
    
    markets_config = {
        "rushing_yards": {
            "features": [
                "rushing_yards_avg_3", "rushing_yards_avg_5", "rushing_yards_avg_10", 
                "rushing_yards_season_avg", "rushing_yards_shrunk_season_avg", "rushing_yards_std_5",
                "carries_avg_3", "carries_avg_5", "carries_avg_10", "carries_season_avg",
                "carries_ewm_3", "rushing_yards_ewm_3",
                "def_rush_yds_allowed_avg_5", "def_rush_yds_allowed_season_avg", "total_line",
                # New Advanced Features
                "rybc_avg_3", "ryac_avg_3",
                "light_box_pct_avg_3", "avg_box_count_avg_3",
                "def_rush_epa_avg_5", "def_run_stop_rate_avg_5",
                "offense_pct_ewm_3", "rz_carry_share_ewm_3", "carry_share_ewm_3", "carry_share_shrunk_season_avg",
                "committee_entropy_avg_3", "implied_spread", "is_turf", "weather_temp", "precipitation_pct",
                "light_box_x_def_rush_epa", "implied_spread_x_rz_carry_share", "carry_share_x_backup_injury",
                "team_plays_per_game_avg_5", "opp_plays_per_game_avg_5", "proe_avg_5", "neutral_script_pass_rate_avg_5",
                "role_stability_score"
            ],
            "positions": ["RB", "WR", "QB"]
        },
        "receiving_yards": {
            "features": [
                "receiving_yards_avg_3", "receiving_yards_avg_5", "receiving_yards_avg_10",
                "receiving_yards_season_avg", "receiving_yards_shrunk_season_avg", "receiving_yards_std_5",
                "targets_avg_3", "targets_avg_5", "targets_avg_10", "targets_season_avg",
                "receptions_avg_3", "receptions_avg_5", "receptions_avg_10", "receptions_season_avg",
                "catch_rate_avg_3", "catch_rate_avg_5", "catch_rate_season_avg",
                "receiving_yards_after_catch_avg_3", "receiving_yards_after_catch_avg_5", "receiving_yards_after_catch_season_avg",
                "def_pass_yds_allowed_avg_5", "def_pass_yds_allowed_season_avg", "total_line",
                # New features
                "wopr_avg_5", "wopr_season_avg", "wopr_ewm_5", "wopr_shrunk_season_avg",
                "target_share_avg_5", "target_share_season_avg", "target_share_ewm_5", "target_share_shrunk_season_avg",
                "air_yards_share_avg_5", "air_yards_share_season_avg", "air_yards_share_ewm_5",
                "receiving_adot_avg_5", "receiving_adot_season_avg",
                "offense_pct_avg_5", "red_zone_targets_avg_5", "rz_efficiency_offense_avg_5",
                "spread_line", "def_pass_epa_allowed_avg_5", "team_qb_epa_per_dropback_avg_5",
                "wopr_x_implied_total", "target_share_x_redistribution", "rz_targets_x_rz_efficiency",
                "team_plays_per_game_avg_5", "opp_plays_per_game_avg_5", "proe_avg_5", "neutral_script_pass_rate_avg_5",
                "role_stability_score"
            ],
            "positions": ["WR", "TE", "RB"]
        },
        "passing_yards": {
            "features": [
                "passing_yards_avg_3", "passing_yards_avg_5", "passing_yards_avg_10",
                "passing_yards_season_avg", "passing_yards_shrunk_season_avg", "passing_yards_std_5",
                "attempts_avg_3", "attempts_avg_5", "attempts_avg_10", "attempts_season_avg",
                "completions_avg_3", "completions_avg_5", "completions_avg_10", "completions_season_avg",
                "passing_cpoe_avg_5", "passing_cpoe_season_avg",
                "epa_per_dropback_avg_5", "epa_per_dropback_season_avg",
                "sack_rate_avg_5", "sack_rate_season_avg",
                "adot_avg_5", "adot_season_avg",
                "def_pass_yds_allowed_avg_5", "def_pass_yds_allowed_season_avg", 
                "total_line", "implied_team_total", "spread_line", "wind",
                "def_pass_epa_allowed_avg_5", "def_pressure_rate_generated_avg_5",
                "days_rest", "is_short_week", "implied_team_total_x_proe", "sack_rate_x_def_pressure",
                "team_plays_per_game_avg_5", "opp_plays_per_game_avg_5", "proe_avg_5", "neutral_script_pass_rate_avg_5",
                "role_stability_score"
            ],
            "positions": ["QB"]
        }
    }
    
    all_results = []
    
    df_test_base = patch_week1_teams(df_test_base)

    os.makedirs("data", exist_ok=True)
    df_features_live = df_test_base
    df_features_live.write_parquet("data/live_features_tmp.parquet")
    os.replace("data/live_features_tmp.parquet", "data/live_features.parquet")
    
    for market, config in markets_config.items():
        print(f"   -> Processing {market}...")
        
        df_odds_market = df_odds.filter(pl.col("market") == market)
        if len(df_odds_market) == 0:
            print(f"      No odds found for {market}")
            continue
            
        train_df = df_features.filter(pl.col("season") != latest_season).filter(pl.col("position").is_in(config["positions"]))
        test_df = df_test_base.filter(pl.col("position").is_in(config["positions"]))
        
        # Apply time-decay sample weights: 2024: 1.0, 2023: 0.85, 2022: 0.70
        import numpy as np
        train_seasons = train_df.select("season").to_series().to_numpy()
        sample_weights = np.where(train_seasons == 2024, 1.0, np.where(train_seasons == 2023, 0.85, 0.70))
        
        model = PlayerPropModel(target=market)
        model.fit(train_df, config["features"], sample_weight=sample_weights)
        
        model.save(f"data/{market}_model_tmp.joblib")
        os.replace(f"data/{market}_model_tmp.joblib", f"data/{market}_model.joblib")
            
        test_df_clean = test_df.drop_nulls(subset=config["features"])
        
        # In live betting evaluation, evaluate each player with their latest available feature vector
        if "is_latest" in test_df_clean.columns:
            latest_stats = test_df_clean.sort(["is_latest", "week"], descending=[True, True]).group_by("player_id").first()
        else:
            latest_stats = test_df_clean.sort("week").group_by("player_id").last()
            
        test_eval = latest_stats.join(df_odds_market.drop(["season", "week"], strict=False), on="player_id", how="inner")
            
        if len(test_eval) > 0:
            lines = test_eval["line"].to_numpy()
            probs_over = model.probability_over_line(test_eval, lines)
            
            df_eval_with_odds = test_eval.select(["player_name", "team", "season", "week", "market", "line", "odds", "side", "espn_id"])
            results = analyze_opportunities(df_eval_with_odds, probs_over)
            all_results.append(results)
    
    if len(all_results) > 0:
        final_results = pl.concat(all_results)
        try:
            from nfl_odds.data.depth_chart import enrich_with_depth_chart
            final_results = enrich_with_depth_chart(final_results)
        except Exception as e:
            print(f"Warning: Could not enrich with depth charts: {e}")

        try:
            from nfl_odds.odds.schedule_manager import get_upcoming_games
            df_sched_w1 = get_upcoming_games(2026, 1)
            sched_map = {}
            for row in df_sched_w1.iter_rows(named=True):
                sched_map[row["home_team"]] = (row["game_id"], row["away_team"])
                sched_map[row["away_team"]] = (row["game_id"], row["home_team"])
            
            game_ids = [sched_map.get(t, (None, None))[0] for t in final_results["team"]]
            opps = [sched_map.get(t, (None, None))[1] for t in final_results["team"]]
            final_results = final_results.with_columns([
                pl.lit(2026).alias("season"),
                pl.lit(1).alias("week"),
                pl.Series("game_id", game_ids),
                pl.Series("opponent", opps)
            ])
        except Exception as e:
            print(f"Warning: Could not attach schedule info: {e}")
            
        final_results.write_parquet("data/live_value_bets_tmp.parquet")
        os.replace("data/live_value_bets_tmp.parquet", "data/live_value_bets.parquet")
        print("Pipeline completed. Results saved to data/live_value_bets.parquet.")

        try:
            from nfl_odds.ai.summary_generator import generate_summaries_for_recommended
            print("\n5. Generating AI Summaries for Recommended Picks (Gemini Flash)...")
            generate_summaries_for_recommended("data/live_value_bets.parquet", "data/live_features.parquet")
        except Exception as e:
            print(f"Warning: Could not generate AI summaries: {e}")

        print("\n🔥 TOP VALUE BETS FOUND (Todos os mercados): 🔥")
        print(final_results.head(15))
    else:
        print("Nenhuma oportunidade avaliada. Verifica o matching de nomes.")

def main():
    parser = argparse.ArgumentParser(description="NFL Odds EV Pipeline")
    parser.add_argument("--live", action="store_true", help="Use live/extracted Betclic odds")
    args = parser.parse_args()
    run_pipeline(live=args.live)

if __name__ == "__main__":
    main()
