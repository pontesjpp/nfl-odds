import os
import polars as pl
from typing import Dict, Any, Optional

TEAM_NAMES = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
    "LAC": "Los Angeles Chargers", "LA": "Los Angeles Rams", "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders"
}

_defense_cache: Dict[str, Dict[str, Any]] = {}

def compute_defense_rankings(season: int = 2026, week: int = 1, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Computa os rankings defensivos de todas as 32 equipes da NFL.
    Regra de negócio:
    - Na 1ª rodada (week <= 1): utiliza as métricas consolidadas da temporada anterior (season - 1, ex: 2025-2026).
    - A partir da 2ª rodada (week >= 2): utiliza estritamente as métricas acumuladas da nova temporada (season, ex: 2026-2027) até week - 1.
    """
    cache_key = f"{season}_{week}"
    if not force_refresh and cache_key in _defense_cache:
        return _defense_cache[cache_key]

    features_path = "data/live_features.parquet"
    if not os.path.exists(features_path):
        return {}

    df_features = pl.read_parquet(features_path)

    # Definir temporada alvo conforme a regra
    is_week_1 = week <= 1
    target_season = (season - 1) if is_week_1 else season
    
    # Filtrar dados para a temporada
    df_s = df_features.filter(pl.col("season") == target_season)
    
    # Se a partir da semana 2, filtrar apenas jogos anteriores à semana atual
    if not is_week_1:
        df_s = df_s.filter(pl.col("week") < week)

    # Fallback seguro: se na semana 2+ ainda não houver jogos computados da nova temporada
    if df_s.is_empty():
        target_season = season - 1
        df_s = df_features.filter(pl.col("season") == target_season)
        source_label = f"Temporada {target_season}-{target_season+1} (Linha de Base Rodada 1)"
        is_fallback = True
    else:
        if is_week_1:
            source_label = f"Temporada {target_season}-{target_season+1} (Linha de Base Rodada 1)"
        else:
            source_label = f"Temporada {target_season}-{target_season+1} (Rodadas 1 a {week - 1})"
        is_fallback = False

    # Pegar o último snapshot disponível de cada defesa adversária no período
    latest_opps = df_s.sort(["opponent_team", "week"]).group_by("opponent_team").tail(1)

    # Mapeamento de métricas defensivas:
    # (coluna, higher_is_better_defense, categoria, nome legível, unidade)
    metrics_config = {
        "def_pass_yds_allowed_season_avg": (False, "pass", "Jardas Passe Cedidas / Jogo", "yds/jogo"),
        "def_rush_yds_allowed_season_avg": (False, "rush", "Jardas Corridas Cedidas / Jogo", "yds/jogo"),
        "def_pass_yds_allowed_avg_5": (False, "pass", "Jardas Passe Cedidas (Últimos 5J)", "yds/jogo"),
        "def_rush_yds_allowed_avg_5": (False, "rush", "Jardas Corridas Cedidas (Últimos 5J)", "yds/jogo"),
        "def_pass_epa_allowed_avg_5": (False, "pass_epa", "EPA Passe Cedido", "EPA/dropback"),
        "def_rush_epa_avg_5": (False, "rush_epa", "EPA Corrida Cedido", "EPA/tentativa"),
        "def_pressure_rate_generated_avg_5": (True, "pressure", "Taxa de Pressão Gerada", "%"),
        "def_run_stop_rate_avg_5": (True, "run_stop", "Taxa de Parada de Corrida", "%")
    }

    team_data: Dict[str, Dict[str, Any]] = {}
    
    for col, (higher_is_better, category, display_name, unit) in metrics_config.items():
        if col not in latest_opps.columns:
            continue
            
        sub = latest_opps.select(["opponent_team", col]).drop_nulls()
        if sub.is_empty():
            continue
            
        league_avg = float(sub[col].mean())
        # Rank 1 = Melhor Defesa (cede menos jardas ou pressiona mais)
        # Rank 32 = Pior Defesa (cede mais jardas ou pressiona menos)
        sorted_df = sub.sort(col, descending=higher_is_better)
        ranked = sorted_df.with_columns(pl.Series("rank", range(1, len(sorted_df) + 1)))
        total_n = len(ranked)

        for row in ranked.iter_rows(named=True):
            t = row["opponent_team"]
            if t not in team_data:
                team_data[t] = {
                    "team": t,
                    "team_name": TEAM_NAMES.get(t, t),
                    "season_source": source_label,
                    "is_fallback": is_fallback,
                    "metrics": {}
                }
                
            r = int(row["rank"])
            val = float(row[col]) if row[col] is not None else 0.0
            diff_pct = ((val - league_avg) / abs(league_avg) * 100.0) if league_avg != 0 else 0.0

            # Classificação por Tier:
            # 1 a 10: Elite (Defesa Muito Forte / Difícil para o Ataque)
            # 11 a 22: Média (Defesa Equilibrada / Neutra)
            # 23 a 32: Vulnerável (Defesa Permissiva / Favorável para Over de Ataque)
            if r <= 10:
                tier = "elite"
                tier_label = "Defesa de Elite"
                badge_type = "elite"
            elif r <= 22:
                tier = "average"
                tier_label = "Defesa Mediana"
                badge_type = "average"
            else:
                tier = "weak"
                tier_label = "Defesa Vulnerável"
                badge_type = "weak"

            team_data[t]["metrics"][col] = {
                "name": display_name,
                "unit": unit,
                "category": category,
                "value": round(val, 2),
                "rank": r,
                "total_teams": total_n,
                "league_avg": round(league_avg, 2),
                "pct_diff_league": round(diff_pct, 1),
                "tier": tier,
                "tier_label": tier_label,
                "badge_type": badge_type,
                "higher_is_better_defense": higher_is_better
            }

    # Calcular Score Composto e Rank Geral 1 a 32
    for t, t_info in team_data.items():
        ranks = [m["rank"] for m in t_info["metrics"].values() if "rank" in m]
        composite = sum(ranks) / len(ranks) if ranks else 16.0
        t_info["composite_score"] = round(composite, 2)

    sorted_teams = sorted(team_data.keys(), key=lambda x: team_data[x]["composite_score"])
    for idx, t in enumerate(sorted_teams, 1):
        team_data[t]["overall_rank"] = idx
        if idx <= 10:
            team_data[t]["overall_tier"] = "elite"
            team_data[t]["overall_tier_label"] = "Defesa de Elite (#1 a #10)"
            team_data[t]["overall_description"] = "Unidade defensiva de elite, muito difícil de ser vazada."
        elif idx <= 22:
            team_data[t]["overall_tier"] = "average"
            team_data[t]["overall_tier_label"] = "Defesa Mediana (#11 a #22)"
            team_data[t]["overall_description"] = "Unidade equilibrada com desempenho na média da NFL."
        else:
            team_data[t]["overall_tier"] = "weak"
            team_data[t]["overall_tier_label"] = "Defesa Vulnerável (#23 a #32)"
            team_data[t]["overall_description"] = "Defesa vulnerável entre as que mais cedem jardas na NFL."

    result = {
        "season_source": source_label,
        "week": week,
        "total_teams": len(team_data),
        "teams": team_data
    }
    
    _defense_cache[cache_key] = result
    return result

def get_team_defense_profile(team_code: str, season: int = 2026, week: int = 1, market: Optional[str] = None, side: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retorna o perfil defensivo detalhado do adversário, incluindo o matchup insight para a aposta.
    """
    if not team_code:
        return None
        
    rankings_obj = compute_defense_rankings(season, week)
    teams = rankings_obj.get("teams", {})
    code = team_code.upper().strip()
    
    t_data = teams.get(code)
    if not t_data:
        return None
        
    metrics = t_data.get("metrics", {})
    
    # Extrair os ranks principais para resumo rápido
    pass_yds_info = metrics.get("def_pass_yds_allowed_season_avg") or metrics.get("def_pass_yds_allowed_avg_5")
    rush_yds_info = metrics.get("def_rush_yds_allowed_season_avg") or metrics.get("def_rush_yds_allowed_avg_5")
    pass_epa_info = metrics.get("def_pass_epa_allowed_avg_5")
    rush_epa_info = metrics.get("def_rush_epa_avg_5")
    pressure_info = metrics.get("def_pressure_rate_generated_avg_5")
    
    # Construir insight contextual para o mercado e lado da aposta
    insight = "Análise neutra baseada nos rankings da liga."
    insight_type = "neutral"
    
    if market in ("passing_yards", "receiving_yards"):
        p_rank = pass_yds_info["rank"] if pass_yds_info else 16
        val = pass_yds_info["value"] if pass_yds_info else 0.0
        avg = pass_yds_info["league_avg"] if pass_yds_info else 0.0
        
        if p_rank >= 23:
            # Defesa frágil contra o passe
            if side == "over":
                insight = f"Cenário muito favorável para OVER: {t_data['team_name']} é a #{p_rank} defesa contra o passe na NFL, cedendo {val} jardas/jogo (acima da média de {avg} jardas)."
                insight_type = "favorable"
            else:
                insight = f"Atenção no UNDER: O adversário cede muitas jardas aéreas (#{p_rank} da liga), permitindo volume expressivo de passes."
                insight_type = "unfavorable"
        elif p_rank <= 10:
            # Defesa forte contra o passe
            if side == "under":
                insight = f"Cenário favorável para UNDER: {t_data['team_name']} possui defesa de elite contra o passe (#{p_rank} da liga), limitando adversários a apenas {val} jardas/jogo."
                insight_type = "favorable"
            else:
                insight = f"Desafio para o OVER: Defesa de elite contra o passe (#{p_rank} na NFL). Confronto de alta dificuldade para jardas aéreas."
                insight_type = "unfavorable"
        else:
            insight = f"Confronto equilibrado: {t_data['team_name']} é a #{p_rank} defesa contra o passe, com médias alinhadas ao padrão da liga ({val} jardas/jogo)."
            insight_type = "neutral"
            
    elif market == "rushing_yards":
        r_rank = rush_yds_info["rank"] if rush_yds_info else 16
        val = rush_yds_info["value"] if rush_yds_info else 0.0
        avg = rush_yds_info["league_avg"] if rush_yds_info else 0.0
        
        if r_rank >= 23:
            # Defesa frágil contra a corrida
            if side == "over":
                insight = f"Cenário muito favorável para OVER: {t_data['team_name']} é a #{r_rank} defesa contra a corrida na NFL, cedendo {val} jardas terrestres/jogo."
                insight_type = "favorable"
            else:
                insight = f"Atenção no UNDER: A defesa terrestre do adversário é permeável (#{r_rank} da NFL), cedendo jardas com facilidade."
                insight_type = "unfavorable"
        elif r_rank <= 10:
            # Defesa forte contra a corrida
            if side == "under":
                insight = f"Cenário favorável para UNDER: {t_data['team_name']} tem uma das melhores defesas terrestres da liga (#{r_rank} na NFL), contendo corridas a {val} jardas/jogo."
                insight_type = "favorable"
            else:
                insight = f"Desafio para o OVER: Defesa muito física contra a corrida (#{r_rank} na NFL, permitindo apenas {val} jardas/jogo)."
                insight_type = "unfavorable"
        else:
            insight = f"Confronto equilibrado: {t_data['team_name']} é a #{r_rank} defesa terrestre da NFL ({val} jardas terrestres cedidas por partida)."
            insight_type = "neutral"

    return {
        "team": t_data["team"],
        "team_name": t_data["team_name"],
        "season_source": t_data["season_source"],
        "is_fallback": t_data.get("is_fallback", False),
        "overall_rank": t_data["overall_rank"],
        "overall_tier": t_data["overall_tier"],
        "overall_tier_label": t_data["overall_tier_label"],
        "overall_description": t_data["overall_description"],
        "composite_score": t_data["composite_score"],
        "summary": {
            "pass_rank": pass_yds_info["rank"] if pass_yds_info else None,
            "pass_yds": pass_yds_info["value"] if pass_yds_info else None,
            "rush_rank": rush_yds_info["rank"] if rush_yds_info else None,
            "rush_yds": rush_yds_info["value"] if rush_yds_info else None,
            "pass_epa_rank": pass_epa_info["rank"] if pass_epa_info else None,
            "rush_epa_rank": rush_epa_info["rank"] if rush_epa_info else None,
            "pressure_rank": pressure_info["rank"] if pressure_info else None,
        },
        "insight": insight,
        "insight_type": insight_type,
        "metrics": metrics
    }
