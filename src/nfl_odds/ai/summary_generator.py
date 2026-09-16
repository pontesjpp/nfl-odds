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
    target_opp = row.get("opponent") or row.get("opponent_team")
    stats = {}
    
    # 1. Market-specific production & defense metrics (primary focus)
    if market == "rushing_yards":
        if "rushing_yards_avg_5" in player_feats and player_feats["rushing_yards_avg_5"] is not None:
            stats["Média Jardas Corridas (Últimos 5J)"] = f"{float(player_feats['rushing_yards_avg_5']):.1f}"
        if "carries_avg_5" in player_feats and player_feats["carries_avg_5"] is not None:
            stats["Média de Tentativas/Corridas (5J)"] = f"{float(player_feats['carries_avg_5']):.1f}"
        if "def_rush_yds_allowed_season_avg" in player_feats and player_feats["def_rush_yds_allowed_season_avg"] is not None:
            stats["Defesa Rival: Jardas Terrestres Cedidas/Jogo"] = f"{float(player_feats['def_rush_yds_allowed_season_avg']):.1f}"
        if "def_rush_yds_allowed_avg_5" in player_feats and player_feats["def_rush_yds_allowed_avg_5"] is not None:
            stats["Defesa Rival: Jardas Cedidas (Tendência Recente 5J)"] = f"{float(player_feats['def_rush_yds_allowed_avg_5']):.1f}"
            
    elif market == "receiving_yards":
        if "receiving_yards_avg_5" in player_feats and player_feats["receiving_yards_avg_5"] is not None:
            stats["Média Jardas Recebidas (Últimos 5J)"] = f"{float(player_feats['receiving_yards_avg_5']):.1f}"
        if "targets_avg_5" in player_feats and player_feats["targets_avg_5"] is not None:
            stats["Média de Alvos/Targets (5J)"] = f"{float(player_feats['targets_avg_5']):.1f}"
        if "def_pass_yds_allowed_season_avg" in player_feats and player_feats["def_pass_yds_allowed_season_avg"] is not None:
            stats["Defesa Rival: Jardas Aéreas Cedidas/Jogo"] = f"{float(player_feats['def_pass_yds_allowed_season_avg']):.1f}"
        if "def_pass_yds_allowed_avg_5" in player_feats and player_feats["def_pass_yds_allowed_avg_5"] is not None:
            stats["Defesa Rival: Jardas Passe Cedidas (5J)"] = f"{float(player_feats['def_pass_yds_allowed_avg_5']):.1f}"
            
    elif market == "passing_yards":
        if "passing_yards_avg_5" in player_feats and player_feats["passing_yards_avg_5"] is not None:
            stats["Média Jardas Passe (Últimos 5J)"] = f"{float(player_feats['passing_yards_avg_5']):.1f}"
        if "attempts_avg_5" in player_feats and player_feats["attempts_avg_5"] is not None:
            stats["Média Passes Tentados (5J)"] = f"{float(player_feats['attempts_avg_5']):.1f}"
        if "def_pass_yds_allowed_season_avg" in player_feats and player_feats["def_pass_yds_allowed_season_avg"] is not None:
            stats["Defesa Rival: Jardas Aéreas Cedidas/Jogo"] = f"{float(player_feats['def_pass_yds_allowed_season_avg']):.1f}"

    # 2. Matchup Vegas Context (only if the features row corresponds to the current opponent)
    feats_opp = player_feats.get("opponent_team")
    if target_opp and feats_opp and feats_opp.upper() == target_opp.upper():
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
            
    return stats

def generate_contextual_risk_factor(
    row: dict,
    stats: dict,
    depth_info: Optional[dict] = None,
    news_info: Optional[dict] = None,
    risk_info: Optional[dict] = None
) -> str:
    player = row.get("full_player_name") or row.get("player_name", "O atleta")
    team = row.get("team", "a equipe")
    opponent = row.get("opponent") or row.get("opponent_team") or "o adversário"
    market = row.get("market", "")
    try:
        line = float(row.get("line", 0.0))
    except (ValueError, TypeError):
        line = 0.0
    side = str(row.get("side", "over")).lower()

    # 1. Informações clínicas e de treinos (apenas se for alerta genuíno de lesão/treino)
    has_medical_alert = False
    medical_headline = ""
    if risk_info and risk_info.get("has_news_alert") and risk_info.get("alert_type") in ("INJURY", "PRACTICE_STATUS"):
        has_medical_alert = True
        medical_headline = risk_info.get("alert_headline") or ""
    elif news_info and news_info.get("injuries"):
        inj = news_info.get("injuries")
        if inj and (isinstance(inj, str) or (isinstance(inj, list) and len(inj) > 0)):
            has_medical_alert = True
            medical_headline = f"Status Médico: {inj}"

    if has_medical_alert and medical_headline:
        if side == "over":
            return (
                f"A questão clínica recente reportada ('{medical_headline}'): caso haja qualquer limitação no número de snaps, "
                f"desconforto durante o aquecimento ou a comissão técnica de {team} adote cautela em situação de placar dilatado, "
                f"a restrição de minutos e toques pode impedir que {player} alcance as {line:.1f} jardas."
            )
        else:
            return (
                f"Apesar do relatório clínico ('{medical_headline}') fortalecer teoricamente o Under, o contraponto reside na hipótese "
                f"do atleta atuar medicado e liberado sem restrição perceptível de snaps, explorando desatenção tática da defesa de {opponent}."
            )

    # 2. Identificação precisa da posição do jogador
    pos_raw = ""
    if depth_info and depth_info.get("depth_chart_pos"):
        pos_raw = str(depth_info["depth_chart_pos"]).upper()
    elif row.get("position"):
        pos_raw = str(row["position"]).upper()
    elif depth_info and depth_info.get("position_title"):
        pos_raw = str(depth_info["position_title"]).upper()

    pos = ""
    if "QB" in pos_raw or "QUARTERBACK" in pos_raw:
        pos = "QB"
    elif "RB" in pos_raw or "RUNNING" in pos_raw or "HALFBACK" in pos_raw or "FULLBACK" in pos_raw:
        pos = "RB"
    elif "TE" in pos_raw or "TIGHT" in pos_raw:
        pos = "TE"
    elif "WR" in pos_raw or "WIDE" in pos_raw or "RECEIVER" in pos_raw:
        pos = "WR"

    if not pos:
        if market == "passing_yards":
            pos = "QB"
        elif market == "rushing_yards":
            if any(name in player for name in ["Allen", "Goff", "Burrow", "Hurts", "Jackson", "Mahomes", "Nix", "Young", "Jones", "Williams", "Maye", "Daniels", "Cousins", "Purdy", "Stroud", "Tagovailoa", "Love", "Prescott", "Lawrence"]):
                pos = "QB"
            else:
                pos = "RB"
        elif market == "receiving_yards":
            if any(name in player for name in ["Kincaid", "LaPorta", "Knox", "Kelce", "Andrews", "Kittle", "Goedert", "Ferguson", "Njoku", "Bowers", "Engram", "Kraft", "Henry", "Freiermuth"]):
                pos = "TE"
            elif any(name in player for name in ["Gibbs", "Cook", "Barkley", "McCaffrey", "Kamara", "Hall", "Taylor", "Bijan", "Kyren", "Jacobs", "Conner", "Walker", "Achane", "Mixon", "Swift", "White"]):
                pos = "RB"
            else:
                pos = "WR"

    # 3. Contexto de Vegas / Game Script
    margin = None
    if "implied_spread" in row and row["implied_spread"] is not None:
        try:
            margin = float(row["implied_spread"])
        except (ValueError, TypeError):
            pass
    elif "Favoritismo / Spread" in stats:
        txt = str(stats["Favoritismo / Spread"])
        if "FAVORITO" in txt:
            margin = 3.5
        elif "UNDERDOG" in txt:
            margin = -3.5

    # 4. Fatores de risco altamente específicos por mercado e arquétipo
    if market == "passing_yards":
        if side == "under":
            if margin and margin < -2.0:
                return (
                    f"Roteiro de jogo adverso precoce (negative game script): se {team} ficar atrás por múltiplas posses de bola no 1º tempo, "
                    f"{player} será forçado a operar em ritmo acelerado (no-huddle/hurry-up) com mais de 40 tentativas de passe no 2º tempo, "
                    f"acumulando jardas de volume puro contra a defesa preventiva de {opponent}."
                )
            else:
                return (
                    f"A vulnerabilidade da secundária de {opponent} contra passes verticais e quebras de tackle (YAC): um único lançamento "
                    f"intermediário de 15 jardas que resulte em 45+ jardas adicionais após a recepção pode quebrar a margem da linha de {line:.1f} em um só lance."
                )
        else: # passing_yards over
            if margin and margin > 2.0:
                return (
                    f"Game script de domínio confortável precoce: caso {team} construa vantagem expressiva no primeiro tempo, o coordenador ofensivo "
                    f"tende a fechar a partida pelo chão para gastar o relógio (four-minute offense), limitando {player} a menos de 24 dropbacks totais."
                )
            else:
                return (
                    f"A pressão agressiva da linha defensiva de {opponent}: blitzes frequentes e colapso rápido do bolsão podem forçar sacks, "
                    f"descartes imediatos de bola e passes de válvula de escape ultra-curtos (baixo aDOT), impedindo a progressão aérea contínua."
                )

    elif market == "rushing_yards":
        if pos == "QB":
            if side == "under":
                if line <= 15.5:
                    return (
                        f"Para uma linha enxuta de apenas {line:.1f} jardas, o principal risco reside em um único scramble não planejado em 3rd & long: "
                        f"se a secundária de {opponent} marcar em cobertura individual (man-to-man) de costas para o lance, {player} pode correr 15 a 20 jardas "
                        f"até a linha lateral e bater a marca em uma única jogada."
                    )
                else:
                    return (
                        f"O dinamismo e atleticismo de {player} em chamadas desenhadas (designed runs / read-option na red zone): um breakdown defensivo "
                        f"nas pontas por parte de {opponent} pode permitir corridas em campo aberto que superem rapidamente as {line:.1f} jardas."
                    )
            else: # QB rushing over
                if line <= 15.5:
                    return (
                        f"A postura estrita de passador de bolso de {player} e a priorização da integridade física: sob pressão, a tendência é o descarte "
                        f"da bola para fora do campo, além do risco de perdas de jardas acumuladas em kneel-downs (ajoelhamentos no final de tempo)."
                    )
                else:
                    return (
                        f"A designação de um linebacker dedicado ('QB spy') por parte da comissão técnica de {opponent} para anular os escapes de {player}, "
                        f"forçando o atleta a permanecer confinado no pocket."
                    )
        else: # RB rushing
            if side == "under":
                if line >= 60.0:
                    return (
                        f"O volume bruto de toques e o desgaste físico imposto contra a frente de {opponent}: mesmo que a defesa rival contenha o ganho "
                        f"médio nos dois primeiros quartos, {player} pode encontrar uma quebra de bloqueio na segunda etapa e disparar para uma corrida de 25+ jardas."
                    )
                else:
                    return (
                        f"Uma alteração não planejada na rotação de backfield de {team} (como cansaço ou desgaste do titular), transferindo 5 a 7 carregadas "
                        f"adicionais entre os tackles para {player} ao longo do segundo tempo."
                    )
            else: # RB rushing over
                if line >= 60.0:
                    return (
                        f"A defesa de {opponent} congestionar as trincheiras com 8 defensores na caixa (stacked box) limitando o ganho antes do contato (RYBC nulo), "
                        f"ou {team} entrar em desvantagem no placar e abandonar o plano de corrida prematuramente."
                    )
                else:
                    return (
                        f"O plano de jogo de {team} concentrar todas as carregadas pesadas de first e second down no running back principal, restringindo {player} "
                        f"a snaps esporádicos de bloqueio e menos de 4 carregadas efetivas."
                    )

    elif market == "receiving_yards":
        if pos == "TE":
            if side == "under":
                return (
                    f"A exploração do meio do campo e da red zone: se {opponent} adotar marcação em zona com linebackers vulneráveis em cobertura, {player} "
                    f"pode acumular 4 a 5 recepções em rotas seam/crosser de 10-12 jardas, quebrando a margem de {line:.1f} jardas."
                )
            else:
                return (
                    f"A exigência tática da comissão de {team} em manter {player} alinhado na linha ofensiva para auxílio em bloqueios de proteção de passe "
                    f"(in-line blocking) contra o pass-rush externo de {opponent}, reduzindo severamente sua taxa de participação em rotas ativas."
                )
        elif pos == "RB":
            if side == "under":
                return (
                    f"A utilização intensiva de passes de válvula de escape (checkdowns e screen passes): caso {opponent} pressione intensamente o quarterback, "
                    f"{player} se tornará a rota de alívio prioritária, acumulando jardas fáceis pós-recepção (YAC) no flat."
                )
            else:
                return (
                    f"A marcação disciplinada dos linebackers de {opponent} nas rotas curtas de flat e a escolha de {team} em canalizar o plano de jogo "
                    f"pelos recebedores abertos no perímetro, tornando os passes para o backfield desnecessários."
                )
        else: # WR
            if line >= 50.0: # WR1 / elite target
                if side == "under":
                    return (
                        f"A concentração e densidade de alvos: como principal referência ofensiva com Target Share acima de 23%, {player} pode atingir "
                        f"as {line:.1f} jardas mesmo sob marcação rígida através de conexões rápidas no slot ou recepções contestadas em 3rd downs."
                    )
                else:
                    return (
                        f"A secundária de {opponent} desenhar marcação dupla constante (bracket coverage / auxílio do safety alto) sobre {player}, forçando o quarterback "
                        f"a progredir suas leituras sistematicamente para o WR2, tight end e running backs."
                    )
            else: # WR2 / WR3 / deep threat
                if side == "under":
                    return (
                        f"A eficiência explosiva por recepção (profundidade de alvo aDOT alta): bastam 1 ou 2 conexões verticais completadas no mano a mano "
                        f"contra o cornerback de {opponent} para que {player} atinja de 30 a 45 jardas em apenas dois snaps."
                    )
                else:
                    return (
                        f"A alta volatilidade de targets no esquema de {team}: em partidas com forte marcação em Cover-2 ou Cover-4 por parte de {opponent}, "
                        f"{player} corre o risco de ser ignorado nas progressões primárias, terminando com menos de 3 alvos totais."
                    )

    # 5. Padrão defensivo se dados não classificados
    if side == "under":
        return f"Uma quebra atípica de marcação na secundária de {opponent} ou ganho inesperado em jogada de big play que supere a linha de {line:.1f} jardas."
    else:
        return f"Ajustes táticos defensivos de {opponent} para neutralizar {player} nas jogadas primárias, forçando a redistribuição da bola para outros atletas de {team}."

def fallback_summary(
    row: dict,
    stats: dict,
    depth_info: Optional[dict] = None,
    news_info: Optional[dict] = None,
    risk_info: Optional[dict] = None
) -> str:
    player = row.get("full_player_name") or row.get("player_name", "Jogador")
    team = row.get("team", "")
    opponent = row.get("opponent", "Adversário")
    market = row.get("market", "")
    line = row.get("line", 0)
    side = row.get("side", "over").lower()
    side_upper = side.upper()
    odds = row.get("odds", 1.90)
    implied_prob = row.get("implied_prob", 0.5) * 100
    prob_win = row.get("prob_win", 0.5) * 100
    edge = row.get("edge", 0) * 100
    ev = row.get("ev_percent", 0)
    fair_odds = row.get("fair_odds", 1.80)
    
    pos_role = "Atleta de rotação"
    if depth_info and depth_info.get("depth_summary"):
        pos_role = depth_info["depth_summary"]
    
    # 1. Tese de Valor
    tese = (
        f"Discrepância matemática quantificada entre a cotação oferecida pelas casas ({odds:.2f}, "
        f"probabilidade implícita de {implied_prob:.1f}%) e a probabilidade estimada pelo modelo quantitativo "
        f"({prob_win:.1f}%, Odd Justa projetada em {fair_odds:.2f}), consolidando um Edge de +{edge:.1f}% e "
        f"Valor Esperado (+EV) de +{ev:.1f}% para a entrada **{side_upper} {line}**. No depth chart oficial de {team}, "
        f"o atleta atua como **{pos_role}**."
    )
    
    # 2. Métrica-Chave contextual
    metric_details = []
    if stats:
        for k, v in list(stats.items())[:3]:
            metric_details.append(f"{k}: {v}")
    
    if market == "rushing_yards":
        if side == "under":
            metrica = (
                f"A defesa de {opponent} apresenta forte integridade nas trincheiras, limitando jardas antes do contato (RYBC) "
                f"e mantendo taxas elevadas de paradas na linha de scrimmage. "
                + (f"Métricas apuradas: {'; '.join(metric_details)}." if metric_details else "Volume recente de toques aponta para rotação compartilhada.")
            )
        else:
            metrica = (
                f"Alta eficiência por tentativa terrestre e taxa consistente de jardas após o contato (RYAC) "
                f"contra a frente defensiva de {opponent}. "
                + (f"Métricas apuradas: {'; '.join(metric_details)}." if metric_details else "Consistência de toques sustenta a linha proposta.")
            )
    elif market == "receiving_yards":
        if side == "under":
            metrica = (
                f"O esquema defensivo de {opponent} prioriza cobertura recuada com safeties altos (Cover-2/Quarters), "
                f"restringindo rotas profundas e limitando separação média por rota corrida. "
                + (f"Métricas registradas: {'; '.join(metric_details)}." if metric_details else "Volume de alvos (Target Share) diluído no ataque.")
            )
        else:
            metrica = (
                f"Elevada participação de rotas ativas (Route Participation) e alinhamento tático favorável "
                f"para explorar as brechas de marcação da secundária de {opponent}. "
                + (f"Métricas apuradas: {'; '.join(metric_details)}." if metric_details else "Capacidade comprovada de conversão e YAC.")
            )
    elif market == "passing_yards":
        if side == "under":
            metrica = (
                f"A defesa de {opponent} gera pressão constante com front-four sem necessidade de blitz, "
                f"forçando passes de release ultra-rápido e reduzindo a profundidade média do alvo (aDOT). "
                + (f"Métricas apuradas: {'; '.join(metric_details)}." if metric_details else "Ritmo cadenciado de dropbacks no confronto.")
            )
        else:
            metrica = (
                f"Eficiência no pocket medida por EPA positivo por dropback e precisão sobre o esperado (CPOE) "
                f"favorável contra o esquema de secundária de {opponent}. "
                + (f"Métricas apuradas: {'; '.join(metric_details)}." if metric_details else "Volume projetado de tentativas em script equilibrado.")
            )
    else:
        metrica = f"As métricas consolidadas do atleta frente ao esquema de {opponent} respaldam a projeção em relação à linha de {line}."
    
    # 3. Cenário de Jogo
    news_ctx = ""
    if risk_info and risk_info.get("has_news_alert"):
        headline = risk_info.get("alert_headline") or (news_info.get("headline") if news_info else "")
        if headline:
            news_ctx = f" Notícia relevante da semana: *{headline}*."
            
    if side == "under":
        cenario = (
            f"O script da partida entre {team} e {opponent} projeta controle de posse e divisão de volume ofensivo. "
            f"Diante das características táticas do adversário, a distribuição de toques tende a limitar o teto de produção "
            f"do atleta abaixo da linha de {line}.{news_ctx}"
        )
    else:
        cenario = (
            f"O fluxo do confronto entre {team} e {opponent} favorece a utilização constante do atleta em momentos decisivos "
            f"(early downs e terceiras descidas intermediárias), permitindo que acumule volume suficiente para superar a linha proposta.{news_ctx}"
        )
        
    # 4. Fatores de Risco / Contraponto altamente dinâmico e contextual
    risco = generate_contextual_risk_factor(row, stats, depth_info, news_info, risk_info)

    return f"""* **Tese de Valor**: {tese}
* **Métrica-Chave**: {metrica}
* **Cenário de Jogo**: {cenario}
* **Fatores de Risco / Contraponto**: {risco}"""

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
        sort_cols = [c for c in ["season", "week"] if c in df_feats.columns]
        df_sorted = df_feats.sort(sort_cols) if sort_cols else df_feats
        
        group_cols = ["player_name"]
        if "team" in df_feats.columns:
            group_cols.append("team")
            
        latest_feats = df_sorted.group_by(group_cols).last()
        for r in latest_feats.iter_rows(named=True):
            p_name = r["player_name"]
            p_team = r.get("team")
            if p_team:
                feats_by_player[(p_name, p_team)] = r
            if p_name not in feats_by_player:
                feats_by_player[p_name] = r
        
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
        is_positive_ev = ev > 0.0
        
        p_news = news_by_player.get(player) or news_by_player.get(display_player) or {}
        corr_news = scout.get_correlated_news(team=team, market=market, target_player_name=display_player)
        
        heuristic_eval = scout.evaluate_risk_heuristic(
            p_news, 
            side=side, 
            market=market, 
            correlated_news=corr_news
        )
        
        if not is_positive_ev:
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
            cached_summ = cached_item.get("ai_summary", "")
            is_stale = (
                "jogada explosiva isolada" in cached_summ
                or "Desvios no plano de jogo" in cached_summ
                or "Fatores de Risco" not in cached_summ
            )
            if not is_stale:
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
            
        p_feats = feats_by_player.get((player, team)) or feats_by_player.get(player, {})
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
                actual_opp = row.get("opponent") or row.get("opponent_team") or p_feats.get("opponent_team", "Adversário")
                prompt = build_analysis_prompt(
                    player_name=display_player,
                    team=team,
                    opponent=actual_opp,
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
