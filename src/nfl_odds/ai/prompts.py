"""
prompts.py — versão com suporte a dupla polaridade (Over vs Under) e inteligência correlacionada

Mudanças principais:
1. SYSTEM_PROMPT ensina explicitamente a dualidade de risco entre OVER e UNDER:
   - No OVER: lesões, treinos limitados, ventos fortes e recebedores lesionados (para QBs)
     são riscos que diminuem a stake (CAUTION/AVOID, multiplier < 1.0).
   - No UNDER: lesões, treinos limitados, snap counts, timeshares e desfalques em alvos
     são catalisadores POSITIVOS que aumentam a convicção do Under (BOOST, multiplier > 1.0).
2. Introduz campos JSON para dimensionamento dinâmico:
   - 'side_favorability': grau de alinhamento com a entrada específica
   - 'recommendation_adjustment': BOOST, MAINTAIN, CAUTION, AVOID
   - 'ai_unit_multiplier': número decimal (0.0 a 1.40)
   - 'ai_sizing_rationale': 1 frase concisa justificando o ajuste de stake
3. Bloco de notícias correlacionadas da equipe (status de recebedores para QB, etc.)
"""

from typing import Optional, List, Dict, Any


SYSTEM_PROMPT = """Você é um analista quantitativo sênior de apostas da NFL especializado em Player Props e Inteligência Esportiva.
Sua missão é explicar, em português do Brasil, por que uma aposta recomendada pelo nosso modelo XGBoost possui
Valor Esperado Positivo (+EV) — com rigor estatístico, prudência calibrada e UMA INTERPRETAÇÃO SEMÂNTICA BIDIRECIONAL das notícias da semana (treinos, lesões, declarações e divisão de toques) EM FUNÇÃO DO LADO DA ENTRADA (OVER vs UNDER).

DIRETRIZES CRÍTICAS DE POLARIDADE (OVER vs UNDER):
O contexto de notícias, lesões e treinos NUNCA deve ser avaliado como 'positivo' ou 'negativo' de forma genérica.
O impacto depende estritamente de estarmos recomendando **OVER** ou **UNDER**:

1. SE A ENTRADA FOR 'OVER':
   - Catalisadores Positivos (BOOST / Multiplier 1.15 a 1.35):
     * Atleta 100% saudável, evolução nos treinos, titularidade incontestável.
     * Reserva imediato fora por lesão (garante maior volume / papel de bellcow).
     * Para QBs: corpo de recebedores completo e saudável contra secundária vulnerável.
     * Clima calmo ou estádio fechado (dome).
   - Fatores de Risco / Penalização (CAUTION / Multiplier 0.50 a 0.75 | AVOID / Multiplier 0.0):
     * Jogador com lesão ativa, treino limitado (Limited) ou dúvida (Questionable).
     * Rotação compartilhada (comitê/timeshare).
     * Para QBs: desfalque ou dúvida no WR1, WR2 ou TE titular da equipe (amputa a eficiência aérea).
     * Clima hostil (vento > 20 mph, chuva torrencial).
     * Em caso de lesão severa (DNP/Doubtful), use 'AVOID' e multiplier 0.0.

2. SE A ENTRADA FOR 'UNDER':
   - Catalisadores Fortemente Favoráveis (BOOST / Multiplier 1.20 a 1.35):
     * Jogador com lesão recente, dores musculares, treino limitado ou status Questionable (se jogar, terá minutagem restrita; se não jogar, aposta é push/void).
     * Rotação compartilhada de backfield / comitê 50/50 reportado pelos técnicos.
     * Para QBs: WR1 ou múltiplos recebedores titulares fora ou limitados (ataque recorre a checkdowns curtos e corridas).
     * Para WRs: QB reserva atuando como titular.
     * Clima adverso (ventos fortes desfavorecem o jogo aéreo).
     * Explique claramente no 'impact_assessment' e 'ai_sizing_rationale' como esse desfalque/limitação blinda e fortalece o UNDER!
   - Fatores de Risco para o Under (CAUTION / Multiplier 0.65 a 0.85):
     * Reserva direto lesionado (jogador titular concentrará todo o volume e toques).
     * Atleta em sequência quente com matchup amplamente favorável.

3. Princípios de Cautela e Probabilidade:
   - Trate Edge e EV como estimativas estatísticas sujeitas a variância — nunca como promessa ou certeza.
   - Use linguagem calibrada: 'aponta para assimetria favorável', 'cenário estatisticamente consistente'.

Formato de Resposta Obrigatório (JSON Estrito):
Sua resposta DEVE ser um objeto JSON válido (sem texto antes ou depois) com a seguinte estrutura:
{
  "has_news_alert": boolean (true se houver lesão, dúvida, treino limitado, desfalque em recebedor ou divisão de volume; false caso contrário),
  "alert_severity": string ("NONE" | "INFO" | "WARNING" | "CRITICAL"),
  "alert_type": string ("NONE" | "INJURY" | "PRACTICE_STATUS" | "TIMESHARE_TARGETS" | "CORRELATED_TARGETS" | "DEPTH_CHANGE"),
  "alert_headline": string (manchete factual de 1 linha com o fato mais relevante da semana),
  "news_context": string (resumo factual dos treinos, declarações da comissão e notícias médicas apuradas),
  "impact_assessment": string (avaliação objetiva de como a notícia impacta a entrada Over/Under específica),
  "side_favorability": string ("HIGHLY_FAVORABLE_FOR_OVER" | "FAVORABLE_FOR_OVER" | "NEUTRAL" | "FAVORABLE_FOR_UNDER" | "HIGHLY_FAVORABLE_FOR_UNDER"),
  "recommendation_adjustment": string ("BOOST" | "MAINTAIN" | "CAUTION" | "AVOID"),
  "ai_unit_multiplier": number (multiplicador de stake sugerido, entre 0.0 e 1.40),
  "ai_sizing_rationale": string (1 frase explicando a razão do ajuste de stake),
  "ai_summary": string (exatamente os 4 tópicos em Markdown explicados abaixo)
}

Diretrizes para o campo 'ai_summary':
Deve conter exatamente 4 tópicos em formato Markdown:
* **Tese de Valor**: Discrepância matemática entre a linha oferecida pela casa e a probabilidade calculada pelo modelo, citando o papel hierárquico no depth chart.
* **Métrica-Chave**: O dado estatístico mais contundente do jogador ou da defesa adversária — priorize métricas avançadas (WOPR, CPOE, EPA, Target Share).
* **Cenário de Jogo**: Como o matchup tático, ritmo, script do jogo E os treinos/notícias recentes (incluindo alvos/companheiros) favorecem o lado da entrada (Over ou Under).
* **Fatores de Risco / Contraponto**: Pelo menos um fator concreto que poderia enfraquecer a tese, integrando explicitamente qualquer incerteza clínica ou divisão de volume apurada na semana.
"""


def format_market_name(market: str) -> str:
    mapping = {
        "rushing_yards": "Jardas Corridas (Rushing Yards)",
        "receiving_yards": "Jardas de Recepção (Receiving Yards)",
        "passing_yards": "Jardas de Passe (Passing Yards)",
    }
    return mapping.get(market, market.replace("_", " ").title())


RUSHING_METRICS = {
    "light_box_pct_avg_3": ("% Caixas Leves da Defesa Rival (últimos 3 jogos)", "pct"),
    "avg_box_count": ("Média de Defensores na Caixa", "num1"),
    "rybc_avg_5": ("Jardas Antes do Contato — RYBC (média 5 jogos)", "num1"),
    "ryac_avg_5": ("Jardas Depois do Contato — RYAC (média 5 jogos)", "num1"),
    "def_rush_epa_avg_5": ("EPA Defensivo Permitido na Corrida (5 jogos)", "num2"),
    "run_stop_rate_allowed": ("Taxa de Paradas na Linha Permitida pela Defesa", "pct"),
    "rz_carry_share_ewm_3": ("Share de Corridas na Red Zone (EWM 3)", "pct"),
    "offense_pct_ewm_3": ("% de Snaps Ofensivos em Campo (EWM 3)", "pct"),
}

RECEIVING_METRICS = {
    "target_share_avg_5": ("Target Share (%)", "pct"),
    "air_yards_share_avg_5": ("Air Yards Share (%)", "pct"),
    "wopr_avg_5": ("WOPR (Weighted Opportunity Rating)", "num2"),
    "receiving_adot_avg_5": ("Profundidade Média do Alvo — aDOT (5 jogos)", "num1"),
    "rz_target_share_avg_5": ("Share de Alvos na Red Zone", "pct"),
    "offense_pct_avg_5": ("% de Snaps Ofensivos em Campo (5 jogos)", "pct"),
}

PASSING_METRICS = {
    "cpoe_avg_5": ("CPOE — Precisão Real vs Esperada (5 jogos)", "num2"),
    "epa_per_dropback_avg_5": ("EPA por Dropback (5 jogos)", "num2"),
    "sack_rate_avg_5": ("Taxa de Sack Sofrida (5 jogos)", "pct"),
    "def_pressure_rate_generated_avg_5": ("Taxa de Pressão Gerada pela Defesa Rival (5 jogos)", "pct"),
}

CONTEXT_METRICS = {
    "weather_temp": ("Temperatura Prevista (°F)", "num1"),
    "wind": ("Velocidade do Vento (mph)", "num1"),
    "precipitation_pct": ("Probabilidade de Precipitação", "pct"),
    "days_rest": ("Dias de Descanso", "int"),
    "is_short_week": ("Semana Curta", "bool"),
    "neutral_script_pass_rate_avg_5": ("Taxa de Passe em Ritmo Neutro (5 jogos)", "pct"),
    "proe_avg_5": ("PROE — Pass Rate Over Expected (5 jogos)", "num2"),
}

MARKET_ADVANCED_MAP = {
    "rushing_yards": RUSHING_METRICS,
    "receiving_yards": RECEIVING_METRICS,
    "passing_yards": PASSING_METRICS,
}

FEATURE_KEY_ALIASES = {
    "rybc_avg_5": ["rybc_avg_5", "rybc_avg_3"],
    "ryac_avg_5": ["ryac_avg_5", "ryac_avg_3"],
    "run_stop_rate_allowed": ["run_stop_rate_allowed", "def_run_stop_rate_avg_5"],
    "rz_target_share_avg_5": ["rz_target_share_avg_5", "red_zone_targets_avg_5"],
    "cpoe_avg_5": ["cpoe_avg_5", "passing_cpoe_avg_5"],
    "avg_box_count": ["avg_box_count", "avg_box_count_avg_3"],
}

MAX_MARKET_METRICS = 8
MAX_CONTEXT_METRICS = 4


def _format_value(val, fmt: str) -> Optional[str]:
    if val is None:
        return None
    try:
        if fmt == "pct":
            return f"{float(val) * 100:.1f}%"
        if fmt == "pct100":
            return f"{float(val):.1f}%"
        if fmt == "num1":
            return f"{float(val):.1f}"
        if fmt == "num2":
            return f"{float(val):.2f}"
        if fmt == "int":
            return f"{int(val)}"
        if fmt == "bool":
            return "Sim" if val else "Não"
    except (TypeError, ValueError):
        return None
    return str(val)


def build_advanced_metrics_text(market: str, advanced_metrics: Optional[dict]) -> str:
    if not advanced_metrics:
        return ""

    market_metrics = MARKET_ADVANCED_MAP.get(market, {})

    market_lines = []
    for key, (label, fmt) in market_metrics.items():
        candidates = FEATURE_KEY_ALIASES.get(key, [key])
        val = None
        for candidate in candidates:
            if candidate in advanced_metrics and advanced_metrics[candidate] is not None:
                val = advanced_metrics[candidate]
                break
        if val is not None:
            formatted = _format_value(val, fmt)
            if formatted is not None:
                market_lines.append(f"- {label}: {formatted}")
        if len(market_lines) >= MAX_MARKET_METRICS:
            break

    context_lines = []
    for key, (label, fmt) in CONTEXT_METRICS.items():
        candidates = FEATURE_KEY_ALIASES.get(key, [key])
        val = None
        for candidate in candidates:
            if candidate in advanced_metrics and advanced_metrics[candidate] is not None:
                val = advanced_metrics[candidate]
                break
        if val is not None:
            formatted = _format_value(val, fmt)
            if formatted is not None:
                context_lines.append(f"- {label}: {formatted}")
        if len(context_lines) >= MAX_CONTEXT_METRICS:
            break

    if not market_lines and not context_lines:
        return ""

    parts = ["\n**Métricas Avançadas do Modelo (Next Gen Stats / FTN / PFR)**:"]
    if market_lines:
        parts.append("\n".join(market_lines))
    if context_lines:
        parts.append("\n**Contexto Ambiental e de Ritmo**:")
        parts.append("\n".join(context_lines))
    parts.append("")
    return "\n".join(parts)


def build_analysis_prompt(
    player_name: str,
    team: str,
    opponent: str,
    market: str,
    line: float,
    side: str,
    odds: float,
    model_prob: float,
    implied_prob: float,
    edge: float,
    ev_percent: float,
    key_stats: dict,
    depth_info: dict = None,
    advanced_metrics: dict = None,
    news_info: dict = None,
    correlated_info: List[dict] = None,
) -> str:
    market_str = format_market_name(market)
    side_str = side.upper()

    stats_lines = []
    for label, val in key_stats.items():
        if val is not None:
            if isinstance(val, float):
                stats_lines.append(f"- {label}: {val:.1f}")
            else:
                stats_lines.append(f"- {label}: {val}")
    stats_text = "\n".join(stats_lines) if stats_lines else "- Estatísticas consolidadas nos modelos."

    depth_text = ""
    if depth_info:
        dc_lines = []
        pos = depth_info.get("depth_chart_pos")
        title = depth_info.get("position_title")
        role = depth_info.get("depth_role")
        rank = depth_info.get("pos_rank")
        exp = depth_info.get("exp_desc")
        college = depth_info.get("college")

        if pos or title:
            dc_lines.append(f"- Papel no Depth Chart: {pos or ''} ({title or ''})")
        if role:
            rank_str = f" (#{rank} no grupo)" if rank else ""
            dc_lines.append(f"- Status no Elenco: {role}{rank_str}")
        if exp:
            col_str = f" | Faculdade: {college}" if college else ""
            dc_lines.append(f"- Experiência: {exp}{col_str}")

        if dc_lines:
            depth_text = "\n**Hierarquia no Depth Chart Oficial (2026/2027)**:\n" + "\n".join(dc_lines) + "\n"

    advanced_text = build_advanced_metrics_text(market, advanced_metrics)

    news_text = ""
    if news_info:
        n_lines = []
        headline = news_info.get("headline")
        story = news_info.get("story")
        injuries = news_info.get("injuries")
        published = news_info.get("published")

        if headline:
            n_lines.append(f"- Manchete Recente: {headline}")
        if published:
            n_lines.append(f"- Data da Notícia: {published}")
        if injuries:
            n_lines.append(f"- Status Médico Oficial: {injuries}")
        if story:
            story_snippet = story[:500] + ("..." if len(story) > 500 else "")
            n_lines.append(f"- Relatório Tático/Treinos: {story_snippet}")

        if n_lines:
            news_text = "\n**Boletim Semanal do Jogador (Treinos, Lesões e Declarações)**:\n" + "\n".join(n_lines) + "\n"

    correlated_text = ""
    if correlated_info:
        corr_lines = []
        for c in correlated_info:
            c_role = c.get("role", "Companheiro")
            c_name = c.get("player_name", "")
            c_news = c.get("news", {})
            c_inj = c_news.get("injuries")
            c_head = c_news.get("headline")
            
            c_status_str = ""
            if c_inj:
                c_status_str = f"[Status Médico: {c_inj}] "
            if c_head:
                c_status_str += f"{c_head}"
            elif not c_status_str:
                c_status_str = "Sem restrições reportadas"
                
            corr_lines.append(f"- {c_role} ({c_name}): {c_status_str}")
            
        if corr_lines:
            correlated_text = "\n**Contexto Correlacionado da Equipe (Recebedores / QB / Backfield)**:\n" + "\n".join(corr_lines) + "\n"

    confidence_note = ""
    if edge < 0.03:
        confidence_note = (
            "\n**Nota**: Edge abaixo de 3% — trate como sinal estatístico de confiança moderada, "
            "não como forte assimetria.\n"
        )

    prompt = f"""Analise a seguinte aposta recomendada da aba RECOMMENDED:

**Jogador**: {player_name} ({team}) vs {opponent}
**Mercado**: {market_str}
**Entrada Recomendada**: {side_str} {line} (Odd: {odds:.2f})
**Probabilidade do Modelo**: {model_prob:.1%} vs **Prob. Implícita da Casa**: {implied_prob:.1%}
**Edge**: +{edge*100:.1f}% | **Valor Esperado (EV)**: +{ev_percent:.1f}%
{confidence_note}{depth_text}{news_text}{correlated_text}
**Estatísticas Básicas e Contexto do Confronto**:
{stats_text}
{advanced_text}
Gere o JSON estrito com a auditoria de risco/notícias (com polaridade exata para {side_str}), dimensionamento sugerido de stake ('ai_unit_multiplier' de 0.0 a 1.40 e 'ai_sizing_rationale') e os 4 tópicos em 'ai_summary', seguindo rigorosamente o prompt de sistema:"""
    return prompt
