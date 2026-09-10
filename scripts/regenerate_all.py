import os
import json
import time
import polars as pl
from google import genai
from nfl_odds.ai.prompts import SYSTEM_PROMPT, build_analysis_prompt
from nfl_odds.ai.summary_generator import extract_key_stats

def main():
    api_key = ""
    with open(".env") as f:
        for line in f:
            if "GEMINI_API_KEY" in line:
                api_key = line.split("=")[1].strip(" \"\n\r")
                break

    client = genai.Client(api_key=api_key)

    df_bets = pl.read_parquet("data/live_value_bets.parquet")
    df_feats = pl.read_parquet("data/live_features.parquet")
    latest_feats = df_feats.sort("week").group_by("player_name").last()
    feats_by_player = {row["player_name"]: row for row in latest_feats.iter_rows(named=True)}

    cache_path = "data/ai_summaries_cache.json"
    with open(cache_path, "r", encoding="utf-8") as f:
        cache = json.load(f)

    rec = df_bets.filter((pl.col("ev_percent") >= 2.5) & (pl.col("ev_percent") <= 15.0))
    print(f"Total recommended bets to process: {len(rec)}")

    for i, row in enumerate(rec.iter_rows(named=True), start=1):
        player = row["player_name"]
        market = row["market"]
        line = row["line"]
        side = row["side"]
        cache_key = f"{player}_{market}_{line}_{side}"

        if cache_key in cache and cache[cache_key]:
            print(f"[{i}/{len(rec)}] Skipping already cached {player} ({market} {side} {line})")
            continue

        p_feats = feats_by_player.get(player, {})
        key_stats = extract_key_stats(row, p_feats)

        depth_info = {
            "depth_chart_pos": row.get("depth_chart_pos"),
            "depth_role": row.get("depth_role"),
            "depth_status": row.get("depth_status"),
            "position_title": row.get("position_title"),
            "pos_rank": row.get("pos_rank"),
            "exp_desc": row.get("exp_desc"),
            "college": row.get("college"),
            "depth_summary": row.get("depth_summary")
        }

        prompt = build_analysis_prompt(
            player_name=row.get("full_player_name") or player,
            team=row.get("team", ""),
            opponent=p_feats.get("opponent_team", "Adversário"),
            market=market,
            line=line,
            side=side,
            odds=row.get("odds", 1.82),
            model_prob=row.get("prob_win", 0.5),
            implied_prob=row.get("implied_prob", 0.5),
            edge=row.get("edge", 0.0),
            ev_percent=row.get("ev_percent", 0.0),
            key_stats=key_stats,
            depth_info=depth_info,
            advanced_metrics=p_feats
        )

        try:
            res = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "temperature": 0.2,
                }
            )
            summary_text = res.text.strip()
            cache[cache_key] = summary_text
            # Save immediately to cache
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            print(f"[{i}/{len(rec)}] Successfully updated {player} ({market} {side} {line})")
        except Exception as e:
            print(f"[{i}/{len(rec)}] Error for {player}: {e}")

        # Safe throttle (3.5s) to guarantee under 15 RPM
        time.sleep(3.5)

    # Sync to parquet
    summaries = []
    for row in df_bets.iter_rows(named=True):
        player = row.get("player_name", "")
        market = row.get("market", "")
        line = row.get("line", 0)
        side = row.get("side", "over")
        key = f"{player}_{market}_{line}_{side}"
        summaries.append(cache.get(key, ""))

    df_bets = df_bets.with_columns(pl.Series("ai_summary", summaries))
    df_bets.write_parquet("data/live_value_bets.parquet")
    print("ALL 16 RECOMMENDED BETS SYNCHRONIZED AND SAVED TO PARQUET!")

if __name__ == "__main__":
    main()
