import os
import json
import time
import httpx
import polars as pl
from pathlib import Path
from typing import Dict, Any, Optional, List

CACHE_PATH = Path("data/player_news_cache.json")
CACHE_TTL_SECONDS = 3 * 3600  # 3 horas de validade para notícias em tempo de jogo

_DEPTH_CHART_CACHE: Optional[Any] = None

def load_news_cache() -> Dict[str, Any]:
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_news_cache(cache: Dict[str, Any]):
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2, default=lambda x: int(x) if hasattr(x, "item") else str(x))
    except Exception as e:
        print(f"Warning: Could not save player news cache: {e}")

def get_team_correlated_depth(team: str) -> Dict[str, Any]:
    """
    Retorna os principais companheiros correlacionados da equipe:
    - pass_catchers: WR1, WR2, WR3, TE1
    - qb1: Quarterback titular
    - rb1 e rb2: Titular e reserva imediato
    """
    global _DEPTH_CHART_CACHE
    if _DEPTH_CHART_CACHE is None:
        try:
            csv_path = "data/depth_charts_2026_2027/nfl_offensive_depth_charts_2026_2027.csv"
            if os.path.exists(csv_path):
                import pandas as pd
                _DEPTH_CHART_CACHE = pd.read_csv(csv_path)
            else:
                import pandas as pd
                _DEPTH_CHART_CACHE = pd.DataFrame()
        except Exception:
            import pandas as pd
            _DEPTH_CHART_CACHE = pd.DataFrame()
            
    if _DEPTH_CHART_CACHE.empty or team not in _DEPTH_CHART_CACHE["team"].values:
        return {"pass_catchers": [], "qb1": None, "rb1": None, "rb2": None}
        
    team_df = _DEPTH_CHART_CACHE[_DEPTH_CHART_CACHE["team"] == team]
    result: Dict[str, Any] = {
        "pass_catchers": [],
        "qb1": None,
        "rb1": None,
        "rb2": None
    }
    
    qb1_rows = team_df[(team_df["position_code"] == "QB") & (team_df["depth_string"] == 1)]
    if not qb1_rows.empty:
        result["qb1"] = {
            "player_name": str(qb1_rows.iloc[0]["player_name"]),
            "espn_id": qb1_rows.iloc[0].get("espn_id"),
            "role": "QB1"
        }
        
    rb1_rows = team_df[(team_df["position_code"] == "RB") & (team_df["depth_string"] == 1)]
    if not rb1_rows.empty:
        result["rb1"] = {
            "player_name": str(rb1_rows.iloc[0]["player_name"]),
            "espn_id": rb1_rows.iloc[0].get("espn_id"),
            "role": "RB1"
        }
        
    rb2_rows = team_df[(team_df["position_code"] == "RB") & (team_df["depth_string"] == 2)]
    if not rb2_rows.empty:
        result["rb2"] = {
            "player_name": str(rb2_rows.iloc[0]["player_name"]),
            "espn_id": rb2_rows.iloc[0].get("espn_id"),
            "role": "RB2"
        }
        
    targets = team_df[team_df["position_code"].isin(["WR1", "WR2", "WR3", "TE"]) & (team_df["depth_string"] == 1)]
    for _, row in targets.iterrows():
        result["pass_catchers"].append({
            "position": str(row["position_code"]),
            "player_name": str(row["player_name"]),
            "espn_id": row.get("espn_id"),
            "role": f"{row['position_code']} Titular"
        })
        
    return result

class PlayerNewsScout:
    """
    Agente Scout responsável por coletar e auditar notícias da semana,
    status de treinos, lesões e divisão de volume/targets (timeshare)
    para jogadores da NFL, com inteligência cruzada de recebedores e QBs.
    """
    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS):
        self.ttl = ttl_seconds
        self.cache = load_news_cache()
        self.client = httpx.Client(
            timeout=8.0,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )

    def get_player_news(self, espn_id: Optional[int], player_name: str, team: str) -> Dict[str, Any]:
        """
        Busca as notícias da semana para um atleta específico via ESPN Athlete API e cache.
        """
        cache_key = f"{espn_id}_{player_name}_{team}"
        now = time.time()
        
        # Verificar cache com TTL
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            cached_at = entry.get("_cached_at", 0)
            if now - cached_at < self.ttl:
                return entry

        news_data: Dict[str, Any] = {
            "player_name": player_name,
            "team": team,
            "espn_id": espn_id,
            "headline": "",
            "story": "",
            "published": "",
            "injuries": [],
            "practice_status": None,
            "has_raw_news": False,
            "_cached_at": now
        }

        # 1. Consulta ESPN Athlete Overview se houver espn_id
        if espn_id:
            try:
                url = f"https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/{espn_id}/overview"
                resp = self.client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    
                    rw = data.get("rotowire") or {}
                    if rw:
                        news_data["headline"] = rw.get("headline", "").strip()
                        news_data["story"] = rw.get("story", "").strip()
                        news_data["published"] = rw.get("published", "").strip()
                        news_data["has_raw_news"] = True

                    injuries = data.get("injuries") or []
                    if injuries:
                        news_data["injuries"] = injuries
                        news_data["has_raw_news"] = True

                    if not news_data["headline"] and data.get("news"):
                        first_news = data["news"][0]
                        news_data["headline"] = first_news.get("headline", "").strip()
                        news_data["story"] = first_news.get("description", "").strip()
                        news_data["published"] = first_news.get("published", "").strip()
                        news_data["has_raw_news"] = True
            except Exception as e:
                print(f"Warning: Failed to fetch ESPN overview for {player_name} (ID: {espn_id}): {e}")

        self.cache[cache_key] = news_data
        save_news_cache(self.cache)
        return news_data

    def get_correlated_news(
        self,
        team: str,
        market: str,
        target_player_name: str
    ) -> List[Dict[str, Any]]:
        """
        Coleta as notícias de companheiros correlacionados:
        - Para QBs (passing_yards): WR1, WR2, WR3, TE1
        - Para WRs/TEs (receiving_yards): QB1
        - Para RBs (rushing_yards): RB2 (reserva imediato)
        """
        corr = get_team_correlated_depth(team)
        correlated_list: List[Dict[str, Any]] = []
        
        target_clean = target_player_name.lower().strip()

        if market == "passing_yards":
            for catcher in corr.get("pass_catchers", []):
                c_name = catcher["player_name"]
                if c_name.lower().strip() == target_clean:
                    continue
                espn_id = catcher.get("espn_id")
                news = self.get_player_news(espn_id=espn_id, player_name=c_name, team=team)
                correlated_list.append({
                    "role": catcher["position"],
                    "player_name": c_name,
                    "news": news
                })

        elif market == "receiving_yards":
            qb1 = corr.get("qb1")
            if qb1 and qb1["player_name"].lower().strip() != target_clean:
                news = self.get_player_news(espn_id=qb1.get("espn_id"), player_name=qb1["player_name"], team=team)
                correlated_list.append({
                    "role": "QB1 Titular",
                    "player_name": qb1["player_name"],
                    "news": news
                })

        elif market == "rushing_yards":
            rb2 = corr.get("rb2")
            if rb2 and rb2["player_name"].lower().strip() != target_clean:
                news = self.get_player_news(espn_id=rb2.get("espn_id"), player_name=rb2["player_name"], team=team)
                correlated_list.append({
                    "role": "RB2 Reserva Direto",
                    "player_name": rb2["player_name"],
                    "news": news
                })
                
        return correlated_list

    def evaluate_risk_heuristic(
        self,
        news: Dict[str, Any],
        side: str = "over",
        market: str = "rushing_yards",
        correlated_news: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Avaliação semântica e probabilística de risco e dimensionamento (OVER vs UNDER),
        apreciando tanto o próprio atleta quanto seus companheiros correlacionados
        (ex: recebedores machucados para QB de passing_yards).
        """
        side_clean = side.lower().strip()
        headline = news.get("headline", "")
        story = news.get("story", "")
        text = f"{headline} {story}".lower()
        injuries = news.get("injuries", [])

        # 1. Checagem de Lesão Oficial no Próprio Jogador
        if injuries:
            inj_item = injuries[0] if isinstance(injuries, list) else injuries
            status = str(inj_item.get("status", "Questionable") if isinstance(inj_item, dict) else inj_item)
            is_critical = any(s in status.lower() for s in ["out", "doubtful", "ir"])
            
            if side_clean == "over":
                return {
                    "has_news_alert": True,
                    "alert_severity": "CRITICAL" if is_critical else "WARNING",
                    "alert_type": "INJURY",
                    "alert_headline": f"Status Médico Oficial: {status}",
                    "impact_assessment": f"Restrição médica ({status}) impõe alto risco para OVER: minutagem controlada ou saída prematura.",
                    "side_favorability": "HIGHLY_FAVORABLE_FOR_UNDER",
                    "recommendation_adjustment": "AVOID" if is_critical else "CAUTION",
                    "ai_unit_multiplier": 0.0 if is_critical else 0.65,
                    "ai_sizing_rationale": "Aposta em OVER vetada por lesão oficial severa." if is_critical else "Stake reduzida em -35% para Over por restrição médica do atleta."
                }
            else:
                return {
                    "has_news_alert": True,
                    "alert_severity": "INFO",
                    "alert_type": "INJURY",
                    "alert_headline": f"Status Médico Oficial: {status}",
                    "impact_assessment": f"Restrição médica ({status}) FAVORECE o UNDER: o atleta atuará com mobilidade e snaps limitados. (Caso não atue, aposta é Push/Void).",
                    "side_favorability": "HIGHLY_FAVORABLE_FOR_UNDER",
                    "recommendation_adjustment": "BOOST",
                    "ai_unit_multiplier": 1.30,
                    "ai_sizing_rationale": "Stake aumentada em +30% no Under: restrição médica reduz o teto produtivo do atleta."
                }

        # 2. Checagem de Treino / Lesão no texto da semana
        critical_inj_keywords = ["did not participate", "dnp", "ruled out", "doubtful", "surgery scheduled", "placed on ir"]
        warning_inj_keywords = ["questionable for sunday", "limited in practice", "game-time decision", "aggravated", "soreness", "groin issue", "hamstring"]

        found_critical = [kw for kw in critical_inj_keywords if kw in text]
        found_warning = [kw for kw in warning_inj_keywords if kw in text]

        if found_critical:
            kw_str = found_critical[0].upper()
            if side_clean == "over":
                return {
                    "has_news_alert": True,
                    "alert_severity": "CRITICAL",
                    "alert_type": "PRACTICE_STATUS" if "dnp" in kw_str.lower() else "INJURY",
                    "alert_headline": headline or f"Alerta Crítico: {kw_str} reportado nos treinos",
                    "impact_assessment": "Ausência em treinos ou lesão grave compromete a viabilidade da aposta em OVER.",
                    "side_favorability": "HIGHLY_FAVORABLE_FOR_UNDER",
                    "recommendation_adjustment": "AVOID",
                    "ai_unit_multiplier": 0.0,
                    "ai_sizing_rationale": "Aposta em OVER vetada por ausência em treinos (DNP/Doubtful)."
                }
            else:
                return {
                    "has_news_alert": True,
                    "alert_severity": "INFO",
                    "alert_type": "PRACTICE_STATUS",
                    "alert_headline": headline or f"Boletim Favorável ao Under: {kw_str} nos treinos",
                    "impact_assessment": "Ausência ou limitação severa nos treinos diminui drasticamente o teto de produção, favorecendo fortemente o UNDER.",
                    "side_favorability": "HIGHLY_FAVORABLE_FOR_UNDER",
                    "recommendation_adjustment": "BOOST",
                    "ai_unit_multiplier": 1.30,
                    "ai_sizing_rationale": "Stake aumentada em +30% no Under: atleta com treinos limitados ou ausência na preparação da semana."
                }

        if found_warning:
            kw_str = found_warning[0].title()
            if side_clean == "over":
                return {
                    "has_news_alert": True,
                    "alert_severity": "WARNING",
                    "alert_type": "INJURY",
                    "alert_headline": headline or f"Atenção Médica: {kw_str} na semana",
                    "impact_assessment": "Treino limitado ou incômodo físico pode reduzir o total de snaps do atleta em campo.",
                    "side_favorability": "FAVORABLE_FOR_UNDER",
                    "recommendation_adjustment": "CAUTION",
                    "ai_unit_multiplier": 0.65,
                    "ai_sizing_rationale": "Stake reduzida em -35% no Over por treino limitado ou incômodo muscular."
                }
            else:
                return {
                    "has_news_alert": True,
                    "alert_severity": "INFO",
                    "alert_type": "INJURY",
                    "alert_headline": headline or f"Treinos Limitados do Atleta ({kw_str})",
                    "impact_assessment": "Treino limitado e incômodos físicos restringem a explosão do atleta, favorecendo a entrada em UNDER.",
                    "side_favorability": "FAVORABLE_FOR_UNDER",
                    "recommendation_adjustment": "BOOST",
                    "ai_unit_multiplier": 1.25,
                    "ai_sizing_rationale": "Stake aumentada em +25% no Under: atleta com treino limitado durante a semana."
                }

        # 3. Checagem de Timeshare / Comitê / Divisão de Toques
        is_starting_qb = "locked in as the team's starting" in text or "new backup" in text
        timeshare_keywords = [
            "timeshare", "committee", "split carries", "split touches", 
            "backfield rotation", "co-starting", "behind ", "no. 2 rb",
            "no. 2 behind", "spelling ", "touch share", "target share"
        ]
        found_timeshare = [kw for kw in timeshare_keywords if kw in text] if not is_starting_qb else []

        if found_timeshare:
            if side_clean == "over":
                return {
                    "has_news_alert": True,
                    "alert_severity": "WARNING",
                    "alert_type": "TIMESHARE_TARGETS",
                    "alert_headline": headline or "Divisão de toques/targets (Timeshare/Comitê) reportada",
                    "impact_assessment": f"Risco elevado para OVER em {market}: a rotação compartilhada limita o teto de volume individual.",
                    "side_favorability": "FAVORABLE_FOR_UNDER",
                    "recommendation_adjustment": "CAUTION",
                    "ai_unit_multiplier": 0.70,
                    "ai_sizing_rationale": "Stake reduzida em -30% no Over devido à divisão de toques/comitê na posição."
                }
            else:
                return {
                    "has_news_alert": True,
                    "alert_severity": "INFO",
                    "alert_type": "TIMESHARE_TARGETS",
                    "alert_headline": headline or "Divisão de toques/targets (Timeshare/Comitê) reportada",
                    "impact_assessment": f"Cenário fortemente favorável para UNDER em {market}: divisão de volume com outros atletas corrobora com a linha reduzida.",
                    "side_favorability": "HIGHLY_FAVORABLE_FOR_UNDER",
                    "recommendation_adjustment": "BOOST",
                    "ai_unit_multiplier": 1.30,
                    "ai_sizing_rationale": "Stake aumentada em +30% no Under: jogador atua em comitê/timeshare com volume fragmentado."
                }

        # 4. Checagem de Notícias de Companheiros Correlacionados
        if correlated_news:
            for item in correlated_news:
                c_role = item.get("role", "")
                c_name = item.get("player_name", "")
                c_news = item.get("news", {})
                c_injuries = c_news.get("injuries", [])
                c_text = f"{c_news.get('headline', '')} {c_news.get('story', '')}".lower()
                
                c_has_inj = bool(c_injuries) or any(k in c_text for k in ["dnp", "ruled out", "doubtful", "questionable", "limited in practice"])
                
                if c_has_inj:
                    if market == "passing_yards":
                        if side_clean == "over":
                            return {
                                "has_news_alert": True,
                                "alert_severity": "WARNING",
                                "alert_type": "CORRELATED_TARGETS",
                                "alert_headline": f"Alvo Principal Desfalcado: {c_name} ({c_role})",
                                "impact_assessment": f"Desfalque ou limitação em recebedor titular ({c_name}, {c_role}) compromete o volume e a eficiência do jogo aéreo.",
                                "side_favorability": "FAVORABLE_FOR_UNDER",
                                "recommendation_adjustment": "CAUTION",
                                "ai_unit_multiplier": 0.70,
                                "ai_sizing_rationale": f"Stake reduzida em -30% no Over de passe: recebedor-chave ({c_name}) lesionado ou limitado."
                            }
                        else:
                            return {
                                "has_news_alert": True,
                                "alert_severity": "INFO",
                                "alert_type": "CORRELATED_TARGETS",
                                "alert_headline": f"Recebedor Principal Desfalcado: {c_name} ({c_role})",
                                "impact_assessment": f"Ausência ou dúvida no recebedor titular ({c_name}) enfraquece o jogo aéreo e FAVORECE o UNDER em jardas de passe.",
                                "side_favorability": "HIGHLY_FAVORABLE_FOR_UNDER",
                                "recommendation_adjustment": "BOOST",
                                "ai_unit_multiplier": 1.25,
                                "ai_sizing_rationale": f"Stake aumentada em +25% no Under de passe: recebedor titular ({c_name}) com limitação médica."
                            }
                            
                    elif market == "receiving_yards" and "qb" in c_role.lower():
                        if side_clean == "over":
                            return {
                                "has_news_alert": True,
                                "alert_severity": "CRITICAL",
                                "alert_type": "CORRELATED_TARGETS",
                                "alert_headline": f"Quarterback Titular Desfalcado: {c_name}",
                                "impact_assessment": f"QB titular ({c_name}) lesionado ou com dúvidas: a entrada de quarterback reserva diminui severamente a precisão e as jardas por alvo.",
                                "side_favorability": "HIGHLY_FAVORABLE_FOR_UNDER",
                                "recommendation_adjustment": "AVOID",
                                "ai_unit_multiplier": 0.50,
                                "ai_sizing_rationale": "Stake reduzida para Over por desfalque do quarterback titular da equipe."
                            }
                        else:
                            return {
                                "has_news_alert": True,
                                "alert_severity": "INFO",
                                "alert_type": "CORRELATED_TARGETS",
                                "alert_headline": f"Quarterback Reserva em Campo: {c_name} desfalcado",
                                "impact_assessment": f"Ataque aéreo comandado por reserva favorece fortemente o UNDER em jardas recebidas para {news.get('player_name')}.",
                                "side_favorability": "HIGHLY_FAVORABLE_FOR_UNDER",
                                "recommendation_adjustment": "BOOST",
                                "ai_unit_multiplier": 1.30,
                                "ai_sizing_rationale": "Stake aumentada em +30% no Under de recepção devido à ausência/limitação do QB titular."
                            }
                            
                    elif market == "rushing_yards" and "rb2" in c_role.lower():
                        if side_clean == "over":
                            return {
                                "has_news_alert": True,
                                "alert_severity": "INFO",
                                "alert_type": "DEPTH_CHANGE",
                                "alert_headline": f"Reserva Imediato Fora: {c_name} (RB2)",
                                "impact_assessment": f"Ausência do reserva direto ({c_name}) garante monopólio de toques (bellcow) para o titular, favorecendo o OVER.",
                                "side_favorability": "HIGHLY_FAVORABLE_FOR_OVER",
                                "recommendation_adjustment": "BOOST",
                                "ai_unit_multiplier": 1.25,
                                "ai_sizing_rationale": "Stake aumentada em +25% no Over de corrida: reserva direto lesionado amplia o volume do titular."
                            }
                        else:
                            return {
                                "has_news_alert": True,
                                "alert_severity": "WARNING",
                                "alert_type": "DEPTH_CHANGE",
                                "alert_headline": f"Reserva Imediato Fora: {c_name} (RB2)",
                                "impact_assessment": f"A ausência de {c_name} concentra carregadas no titular, representando risco considerável para a aposta em UNDER.",
                                "side_favorability": "FAVORABLE_FOR_OVER",
                                "recommendation_adjustment": "CAUTION",
                                "ai_unit_multiplier": 0.75,
                                "ai_sizing_rationale": "Stake reduzida em -25% no Under de corrida: reserva fora concentra todas as carregadas no titular."
                            }

        # 5. Notícias fortemente positivas / Titularidade Absoluta / Bom Momento
        positive_indicators = [
            "positive reviews", "looked sharp", "sharp in practice", "high note", "crisp in practice",
            "impressive", "full participant", "voted captain", "healthy and ready", "locked in as",
            "starter on the heels", "new backup in", "signed a two-year", "solid camp"
        ]
        is_positive = any(pi in text for pi in positive_indicators)

        if is_positive:
            if side_clean == "over":
                return {
                    "has_news_alert": False,
                    "alert_severity": "INFO",
                    "alert_type": "NONE",
                    "alert_headline": headline or "Titularidade absoluta e excelente forma física reportada",
                    "impact_assessment": "Atleta em ótima condição física, titularidade consolidada e bom ritmo nos treinos favorecem a linha de OVER.",
                    "side_favorability": "FAVORABLE_FOR_OVER",
                    "recommendation_adjustment": "BOOST",
                    "ai_unit_multiplier": 1.20,
                    "ai_sizing_rationale": "Stake aumentada em +20% no Over por titularidade plena e excelente forma nos treinos."
                }
            else:
                return {
                    "has_news_alert": False,
                    "alert_severity": "NONE",
                    "alert_type": "NONE",
                    "alert_headline": headline or "Atleta saudável e com titularidade plena",
                    "impact_assessment": "Atleta em pleno vigor físico; o Under se apoia na linha estipulada pela casa e na solidez da defesa rival.",
                    "side_favorability": "NEUTRAL",
                    "recommendation_adjustment": "MAINTAIN",
                    "ai_unit_multiplier": 0.90,
                    "ai_sizing_rationale": "Stake mantida com cautela moderada (-10%) no Under diante da saúde plena do jogador."
                }

        # 6. Neutro / Padrão
        return {
            "has_news_alert": False,
            "alert_severity": "NONE",
            "alert_type": "NONE",
            "alert_headline": headline[:140] if headline else "",
            "impact_assessment": "Sem relatos clínicos adversos ou alterações na hierarquia ofensiva da semana.",
            "side_favorability": "NEUTRAL",
            "recommendation_adjustment": "MAINTAIN",
            "ai_unit_multiplier": 1.00,
            "ai_sizing_rationale": "Alocação padrão baseada no modelo quantitativo (sem desvios contextuais na semana)."
        }

    def batch_scout_recommended(
        self,
        df_bets: pl.DataFrame
    ) -> Dict[str, Dict[str, Any]]:
        """
        Executa a pesquisa e coleta de notícias para os jogadores únicos recomendados
        (EV entre 2.5% e 15.0%) E seus companheiros correlacionados (recebedores para QB, QB para WR, etc).
        Retorna dicionário mapeado por nome do atleta.
        """
        if df_bets.is_empty():
            return {}

        df_rec = df_bets.filter(
            (pl.col("ev_percent") >= 2.5) & (pl.col("ev_percent") <= 15.0)
        )
        if df_rec.is_empty():
            return {}

        unique_players = df_rec.select([
            "player_name", "full_player_name", "team", "espn_id"
        ]).unique()

        print(f"-> [NewsScout] Iniciando varredura semanal inteligente para {len(unique_players)} atletas recomendados...")
        results: Dict[str, Any] = {}

        # 1. Coleta direta dos atletas recomendados
        for row in unique_players.iter_rows(named=True):
            p_name = row.get("player_name", "")
            full_name = row.get("full_player_name") or p_name
            team = row.get("team", "")
            espn_id = row.get("espn_id")
            if espn_id is not None:
                try:
                    espn_id = int(espn_id)
                except (ValueError, TypeError):
                    espn_id = None

            news = self.get_player_news(espn_id=espn_id, player_name=full_name, team=team)
            results[p_name] = news
            if full_name != p_name:
                results[full_name] = news

            headline = news.get("headline")
            if headline:
                print(f"   ✓ [News] {full_name} ({team}): {headline[:75]}...")

        # 2. Coleta dos companheiros correlacionados (QBs, WRs, RBs de apoio)
        teams_in_rec = unique_players.select("team").drop_nulls().unique()["team"].to_list()
        for t in teams_in_rec:
            corr = get_team_correlated_depth(t)
            # Pass catchers
            for catcher in corr.get("pass_catchers", []):
                c_name = catcher["player_name"]
                if c_name not in results:
                    c_id = catcher.get("espn_id")
                    if c_id:
                        try:
                            c_id = int(c_id)
                        except (ValueError, TypeError):
                            c_id = None
                    results[c_name] = self.get_player_news(espn_id=c_id, player_name=c_name, team=t)
            # QB1
            qb1 = corr.get("qb1")
            if qb1 and qb1["player_name"] not in results:
                q_id = qb1.get("espn_id")
                if q_id:
                    try:
                        q_id = int(q_id)
                    except (ValueError, TypeError):
                        q_id = None
                results[qb1["player_name"]] = self.get_player_news(espn_id=q_id, player_name=qb1["player_name"], team=t)
            # RB2
            rb2 = corr.get("rb2")
            if rb2 and rb2["player_name"] not in results:
                r_id = rb2.get("espn_id")
                if r_id:
                    try:
                        r_id = int(r_id)
                    except (ValueError, TypeError):
                        r_id = None
                results[rb2["player_name"]] = self.get_player_news(espn_id=r_id, player_name=rb2["player_name"], team=t)

        return results
