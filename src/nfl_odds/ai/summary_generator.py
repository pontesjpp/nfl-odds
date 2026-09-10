import os
import json
import re
import polars as pl
from pathlib import Path
from typing import Optional, Dict, Any, List

from nfl_odds.ai.prompts import SYSTEM_PROMPT, build_analysis_prompt
from nfl_odds.data.depth_chart import enrich_with_depth_chart
from nfl_odds.ai.news_scout import PlayerNewsScout

CACHE_PATH = Path("data/ai_summaries_cache.json")

def load_cache() -> Dict[str, Any]:
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache: Dict[str, Any]):
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: Could not save AI cache: {e}")

def get_api_key() -> Optional[str]:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return api_key.strip().strip('"').strip("'")
    
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if k in ["GEMINI_API_KEY", "GOOGLE_API_KEY"]:
                        return v.strip().strip('"').strip("'")
    return None

def extract_key_stats(row: dict, player_feats: Optional[dict]) -> dict:
    if not player_feats:
        return {}
        
    market = row.get("market", "")
    stats = {}
    
    if "opponent_team" in player_feats:
        stats["Adversário"] = player_feats["opponent_team"]
    if "implied_team_total" in player_feats and player_feats["implied_team_total"] is not None:
        stats["Pontos Projetados do Time"] = player_feats["implied_team_total"]
    if "implied_spread" in player_feats and player_feats["implied_spread"] is not None:
        margin = player_feats["implied_spread"]
        if isinstance(margin, (int, float)):
            betting_spread = -margin
            if margin > 0.5:
                stats["Favoritismo / Spread"] = f"FAVORITO por {margin:.1f} pontos (Spread Vegas: {betting_spread:+.1f})"
            elif margin < -0.5:
                stats["Favoritismo / Spread"] = f"UNDERDOG / ZEBRA por {abs(margin):.1f} pontos (Spread Vegas: {betting_spread:+.1f})"
            else:
                stats["Favoritismo / Spread"] = "Equilibrado (Pickem 0.0)"
        else:
            stats["Favoritismo / Spread"] = str(margin)
        
    if market == "rushing_yards":
        if "rushing_yards_avg_5" in player_feats:
            stats["Média Jardas Corridas (Últimos 5J)"] = player_feats["rushing_yards_avg_5"]
        if "carries_avg_5" in player_feats:
            stats["Média de Tentativas/Corridas (5J)"] = player_feats["carries_avg_5"]
        if "def_rush_yds_allowed_season_avg" in player_feats:
            stats["Defesa Rival: Jardas Terrestres Cedidas/Jogo"] = player_feats["def_rush_yds_allowed_season_avg"]
        if "def_rush_yds_allowed_avg_5" in player_feats:
            stats["Defesa Rival: Jardas Cedidas (Tendência Recente 5J)"] = player_feats["def_rush_yds_allowed_avg_5"]
            
    elif market == "receiving_yards":
        if "receiving_yards_avg_5" in player_feats:
            stats["Média Jardas Recebidas (Últimos 5J)"] = player_feats["receiving_yards_avg_5"]
        if "targets_avg_5" in player_feats:
            stats["Média de Alvos/Targets (5J)"] = player_feats["targets_avg_5"]
        if "def_pass_yds_allowed_season_avg" in player_feats:
            stats["Defesa Rival: Jardas Aéreas Cedidas/Jogo"] = player_feats["def_pass_yds_allowed_season_avg"]
        if "def_pass_yds_allowed_avg_5" in player_feats:
            stats["Defesa Rival: Jardas Passe Cedidas (5J)"] = player_feats["def_pass_yds_allowed_avg_5"]
            
    elif market == "passing_yards":
        if "passing_yards_avg_5" in player_feats:
            stats["Média Jardas Passe (Últimos 5J)"] = player_feats["passing_yards_avg_5"]
        if "attempts_avg_5" in player_feats:
            stats["Média Passes Tentados (5J)"] = player_feats["attempts_avg_5"]
        if "def_pass_yds_allowed_season_avg" in player_feats:
            stats["Defesa Rival: Jardas Aéreas Cedidas/Jogo"] = player_feats["def_pass_yds_allowed_season_avg"]
            
    return stats

def fallback_summary(
    row: dict,
    stats: dict,
    depth_info: Optional[dict] = None,
    news_info: Optional[dict] = None,
    risk_info: Optional[dict] = None
) -> str:
    player = row.get("full_player_name") or row.get("player_name", "Jogador")
    line = row.get("line", 0)
    side = row.get("side", "over").upper()
    edge = row.get("edge", 0) * 100
    ev = row.get("ev_percent", 0)
    
    dc_phrase = ""
    if depth_info and depth_info.get("depth_summary"):
        dc_phrase = f" No depth chart oficial da equipe, o atleta atua como **{depth_info['depth_summary']}**."
    
    news_risk_phrase = ""
    if risk_info and risk_info.get("has_news_alert"):
        headline = risk_info.get("alert_headline") or (news_info.get("headline") if news_info else "")
        if headline:
            news_risk_phrase = f" **Contexto da semana ({side})**: {headline}."
            
    return f"""* **Tese de Valor**: O modelo matemático aponta para uma assimetria favorável com estimativa de +{edge:.1f}% de edge e valor esperado (+EV) projetado em +{ev:.1f}% para a entrada **{side} {line}**.{dc_phrase}
* **Métrica-Chave**: O volume recente do atleta e as métricas defensivas consolidadas sustentam a projeção em relação à linha proposta pelas casas de apostas.
* **Cenário de Jogo**: A projeção de pontos e ritmo esperado da partida indicam que a minutagem e o uso ofensivo deste jogador alinham-se com a entrada {side}.
* **Fatores de Risco / Contraponto**: A variância natural de amostras recentes e possíveis desvios táticos no plano de jogo adversário representam riscos estatísticos inerentes à aposta.{news_risk_phrase}"""

def parse_llm_json_response(raw_text: str) -> Optional[Dict[str, Any]]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
        
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
        
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
            
    return None

def generate_summaries_for_recommended(
    bets_path: str = "data/live_value_bets.parquet",
    features_path: str = "data/live_features.parquet",
    model_name: str = None
) -> pl.DataFrame:
    if not os.path.exists(bets_path):
        print(f"No bets file found at {bets_path}")
        return pl.DataFrame()
        
    df_bets = pl.read_parquet(bets_path)
    if df_bets.is_empty():
        return df_bets

    if "depth_chart_pos" not in df_bets.columns:
        df_bets = enrich_with_depth_chart(df_bets)
        
    df_feats = pl.read_parquet(features_path) if os.path.exists(features_path) else None
    
    scout = PlayerNewsScout()
    news_by_player = scout.batch_scout_recommended(df_bets)
    
    cache = load_cache()
    model_name = model_name or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    api_key = get_api_key()
    
    client = None
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            print(f"-> Google Gemini Client initialized successfully (Model: {model_name}).")
        except Exception as e:
            print(f"Warning: Failed to initialize Google GenAI Client: {e}")
    else:
        print("-> Notice: GEMINI_API_KEY not set. Using heuristic news audit & sizing.")
        
    feats_by_player = {}
    if df_feats is not None:
        latest_feats = df_feats.sort("week").group_by("player_name").last()
        feats_by_player = {row["player_name"]: row for row in latest_feats.iter_rows(named=True)}
        
    has_news_alerts = []
    alert_severities = []
    alert_types = []
    alert_headlines = []
    news_contexts = []
    impact_assessments = []
    side_favorabilities = []
    recommendation_adjustments = []
    ai_unit_multipliers = []
    ai_sizing_rationales = []
    summaries = []
    
    for row in df_bets.iter_rows(named=True):
        player = row.get("player_name", "")
        display_player = row.get("full_player_name") or player
        team = row.get("team", "")
        market = row.get("market", "")
        line = row.get("line", 0)
        side = row.get("side", "over")
        ev = row.get("ev_percent", 0.0)
        
        cache_key = f"{player}_{market}_{line}_{side}_v2"
        is_recommended = 2.5 <= ev <= 15.0
        
        p_news = news_by_player.get(player) or news_by_player.get(display_player) or {}
        corr_news = scout.get_correlated_news(team=team, market=market, target_player_name=display_player)
        
        heuristic_eval = scout.evaluate_risk_heuristic(
            p_news, 
            side=side, 
            market=market, 
            correlated_news=corr_news
        )
        
        if not is_recommended:
            has_news_alerts.append(False)
            alert_severities.append("NONE")
            alert_types.append("NONE")
            alert_headlines.append("")
            news_contexts.append("")
            impact_assessments.append("")
            side_favorabilities.append("NEUTRAL")
            recommendation_adjustments.append("MAINTAIN")
            ai_unit_multipliers.append(1.0)
            ai_sizing_rationales.append("")
            summaries.append("")
            continue
            
        cached_item = cache.get(cache_key)
        if cached_item and isinstance(cached_item, dict) and cached_item.get("gemini_analyzed"):
            has_news_alerts.append(cached_item.get("has_news_alert", False))
            alert_severities.append(cached_item.get("alert_severity", "NONE"))
            alert_types.append(cached_item.get("alert_type", "NONE"))
            alert_headlines.append(cached_item.get("alert_headline", ""))
            news_contexts.append(cached_item.get("news_context", p_news.get("story", "")))
            impact_assessments.append(cached_item.get("impact_assessment", ""))
            side_favorabilities.append(cached_item.get("side_favorability", "NEUTRAL"))
            recommendation_adjustments.append(cached_item.get("recommendation_adjustment", "MAINTAIN"))
            ai_unit_multipliers.append(float(cached_item.get("ai_unit_multiplier", 1.0)))
            ai_sizing_rationales.append(cached_item.get("ai_sizing_rationale", ""))
            summaries.append(cached_item.get("ai_summary", ""))
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
        
        result_item: Dict[str, Any] = {
            "has_news_alert": heuristic_eval["has_news_alert"],
            "alert_severity": heuristic_eval["alert_severity"],
            "alert_type": heuristic_eval["alert_type"],
            "alert_headline": heuristic_eval["alert_headline"],
            "news_context": p_news.get("story", "") or p_news.get("headline", ""),
            "impact_assessment": heuristic_eval["impact_assessment"],
            "side_favorability": heuristic_eval["side_favorability"],
            "recommendation_adjustment": heuristic_eval["recommendation_adjustment"],
            "ai_unit_multiplier": heuristic_eval["ai_unit_multiplier"],
            "ai_sizing_rationale": heuristic_eval["ai_sizing_rationale"],
            "ai_summary": "",
            "gemini_analyzed": False
        }
        
        if client:
            try:
                prompt = build_analysis_prompt(
                    player_name=display_player,
                    team=team,
                    opponent=p_feats.get("opponent_team", "Adversário"),
                    market=market,
                    line=line,
                    side=side,
                    odds=row.get("odds", 1.90),
                    model_prob=row.get("prob_win", 0.5),
                    implied_prob=row.get("implied_prob", 0.5),
                    edge=row.get("edge", 0.0),
                    ev_percent=ev,
                    key_stats=key_stats,
                    depth_info=depth_info,
                    advanced_metrics=p_feats,
                    news_info=p_news,
                    correlated_info=corr_news
                )
                
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={
                        "system_instruction": SYSTEM_PROMPT,
                        "temperature": 0.1,
                        "response_mime_type": "application/json"
                    }
                )
                raw_text = response.text.strip()
                parsed_json = parse_llm_json_response(raw_text)
                
                if parsed_json and "ai_summary" in parsed_json:
                    result_item["has_news_alert"] = bool(parsed_json.get("has_news_alert", False))
                    result_item["alert_severity"] = str(parsed_json.get("alert_severity", "NONE"))
                    result_item["alert_type"] = str(parsed_json.get("alert_type", "NONE"))
                    result_item["alert_headline"] = str(parsed_json.get("alert_headline", p_news.get("headline", "")))
                    result_item["news_context"] = str(parsed_json.get("news_context", result_item["news_context"]))
                    result_item["impact_assessment"] = str(parsed_json.get("impact_assessment", ""))
                    result_item["side_favorability"] = str(parsed_json.get("side_favorability", heuristic_eval["side_favorability"]))
                    result_item["recommendation_adjustment"] = str(parsed_json.get("recommendation_adjustment", "MAINTAIN"))
                    
                    m_val = parsed_json.get("ai_unit_multiplier")
                    if m_val is not None:
                        try:
                            result_item["ai_unit_multiplier"] = max(0.0, min(1.40, float(m_val)))
                        except (ValueError, TypeError):
                            result_item["ai_unit_multiplier"] = heuristic_eval["ai_unit_multiplier"]
                    else:
                        result_item["ai_unit_multiplier"] = heuristic_eval["ai_unit_multiplier"]
                        
                    result_item["ai_sizing_rationale"] = str(parsed_json.get("ai_sizing_rationale", heuristic_eval["ai_sizing_rationale"]))
                    result_item["ai_summary"] = str(parsed_json.get("ai_summary", raw_text))
                    result_item["gemini_analyzed"] = True
                else:
                    result_item["ai_summary"] = raw_text
                    result_item["gemini_analyzed"] = True
                    
                cache[cache_key] = result_item
                save_cache(cache)
                flag_str = f" [ALERT: {result_item['alert_type']}] ({result_item['recommendation_adjustment']} {result_item['ai_unit_multiplier']}x)"
                print(f"   [Gemini] Análise bidirecional concluída para {display_player} ({side.upper()} {line}){flag_str}")
                import time
                time.sleep(4.1)
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    print(f"   [Gemini 429] Limite de 15 RPM atingido para {display_player}. Aguardando 15s...")
                    import time
                    time.sleep(15)
                else:
                    print(f"   [Gemini Notice/Fallback] For {display_player}: {e}")
                result_item["ai_summary"] = fallback_summary(row, key_stats, depth_info, p_news, heuristic_eval)
                cache[cache_key] = result_item
                save_cache(cache)
        else:
            result_item["ai_summary"] = fallback_summary(row, key_stats, depth_info, p_news, heuristic_eval)
            cache[cache_key] = result_item
            
        has_news_alerts.append(result_item["has_news_alert"])
        alert_severities.append(result_item["alert_severity"])
        alert_types.append(result_item["alert_type"])
        alert_headlines.append(result_item["alert_headline"])
        news_contexts.append(result_item["news_context"])
        impact_assessments.append(result_item["impact_assessment"])
        side_favorabilities.append(result_item["side_favorability"])
        recommendation_adjustments.append(result_item["recommendation_adjustment"])
        ai_unit_multipliers.append(result_item["ai_unit_multiplier"])
        ai_sizing_rationales.append(result_item["ai_sizing_rationale"])
        summaries.append(result_item["ai_summary"])
        
    save_cache(cache)
    
    df_bets = df_bets.with_columns([
        pl.Series("has_news_alert", has_news_alerts, dtype=pl.Boolean),
        pl.Series("alert_severity", alert_severities, dtype=pl.Utf8),
        pl.Series("alert_type", alert_types, dtype=pl.Utf8),
        pl.Series("alert_headline", alert_headlines, dtype=pl.Utf8),
        pl.Series("news_context", news_contexts, dtype=pl.Utf8),
        pl.Series("impact_assessment", impact_assessments, dtype=pl.Utf8),
        pl.Series("side_favorability", side_favorabilities, dtype=pl.Utf8),
        pl.Series("recommendation_adjustment", recommendation_adjustments, dtype=pl.Utf8),
        pl.Series("ai_unit_multiplier", ai_unit_multipliers, dtype=pl.Float64),
        pl.Series("ai_sizing_rationale", ai_sizing_rationales, dtype=pl.Utf8),
        pl.Series("ai_summary", summaries, dtype=pl.Utf8)
    ])
    
    df_bets.write_parquet(bets_path)
    print(f"-> Successfully updated {bets_path} with dual-polarity news alerts, multipliers, and rationales.")
    
    return df_bets

if __name__ == "__main__":
    generate_summaries_for_recommended()
