"""
dynamic_sizing.py — Motor de Dimensionamento Dinâmico e Inteligente de Unidades

Princípios Quantitativos & Regras de Negócio:
1. Filtro Estrito: Apenas apostas com 2.5% <= EV <= 15.0% são elegíveis.
2. Unidades Base (U_base):
   - EV entre 2.5% e 4.9%: 0.75u
   - EV entre 5.0% e 9.9%: 1.00u
   - EV entre 10.0% e 15.0%: 1.25u
   - Odds Adjustment: Leve amortecimento em odds longas (> 2.20) para conter variância.
3. Penalidade de Cauda / Z-Distance (P_cauda):
   - z > 1.5 sigma: 0.75x (proteção contra extrapolação de quantis)
   - z > 1.0 sigma: 0.90x
   - z <= 1.0 sigma: 1.00x
4. Multiplicador Semântico da IA (M_IA):
   - Avalia a polaridade OVER vs UNDER:
     * No Over: lesões/comitês penalizam (0.50x a 0.75x ou AVOID 0.0x); saúde plena alavanca (1.20x a 1.35x).
     * No Under: lesões/comitês/desfalques de recebedores favorecem o Under (1.20x a 1.35x); saúde plena modera (0.80x a 0.90x).
5. Travas Operacionais:
   - Piso: 0.50u (apostas que resultarem em < 0.50u são descartadas ou arredondadas).
   - Teto: 2.50u (preservação de banca contra eventos de cauda).
   - Discretização: Arredondamento para múltiplos exatos de 0.25u (0.50u, 0.75u, 1.00u, 1.25u, 1.50u, 1.75u, 2.00u, 2.50u).
"""

from typing import Dict, Any, Optional, List, Tuple
import math


def calculate_smart_units(
    ev_percent: float,
    odds: float = 1.85,
    prob_win: float = 0.55,
    side: str = "over",
    market: str = "rushing_yards",
    z_distance: Optional[float] = None,
    ai_multiplier: Optional[float] = 1.0,
    recommendation_adjustment: str = "MAINTAIN",
    ai_sizing_rationale: Optional[str] = None,
    apply_high_ev_haircut: bool = True
) -> Dict[str, Any]:
    """
    Calcula a alocação dinâmica de unidades para uma aposta específica.
    Aplica haircut prudencial de 0.75x para picks com EV > 8.0% para conter
    sobre-alocação em probabilidades extremas potencialmente descalibradas.
    """
    # -------------------------------------------------------------
    # 1. Filtro Estrito de EV (2.5% a 15.0%)
    # -------------------------------------------------------------
    if ev_percent is None or ev_percent < 2.5 or ev_percent > 15.0:
        return {
            "final_units": 0.0,
            "base_units": 0.0,
            "tail_penalty": 1.0,
            "high_ev_haircut": 1.0,
            "ai_multiplier": 0.0,
            "status": "EXCLUDED_BY_EV_FILTER",
            "reason": f"EV de {ev_percent:.1f}% fora do intervalo estrito de 2.5% a 15.0%."
        }

    # -------------------------------------------------------------
    # 2. Veto Direto da IA (AVOID ou Multiplier Zero)
    # -------------------------------------------------------------
    adj_clean = (recommendation_adjustment or "MAINTAIN").upper().strip()
    m_val = float(ai_multiplier) if ai_multiplier is not None else 1.0
    
    if adj_clean == "AVOID" or m_val <= 0.0:
        return {
            "final_units": 0.0,
            "base_units": 1.0,
            "tail_penalty": 1.0,
            "high_ev_haircut": 1.0,
            "ai_multiplier": 0.0,
            "status": "VETOED_BY_AI",
            "reason": ai_sizing_rationale or "Aposta vetada pela auditoria de risco da IA."
        }

    # -------------------------------------------------------------
    # 3. Base Quantitativa Normalizada (U_base) & Haircut de Alto EV
    # -------------------------------------------------------------
    high_ev_haircut = 0.75 if (apply_high_ev_haircut and ev_percent > 8.0) else 1.00

    if ev_percent < 5.0:
        base_units = 0.75
    elif ev_percent < 10.0:
        base_units = 1.00
    else:
        base_units = 1.00 if apply_high_ev_haircut else 1.25

    # Amortecimento em odds longas (> 2.20) para conter variância matemática
    if odds > 2.20:
        base_units *= 0.90
    elif odds < 1.65:
        base_units *= 0.95

    # -------------------------------------------------------------
    # 4. Penalidade de Cauda / Extrapolação de Quantis (P_cauda)
    # -------------------------------------------------------------
    tail_penalty = 1.00
    if z_distance is not None and not math.isnan(z_distance):
        if z_distance > 1.5:
            tail_penalty = 0.75
        elif z_distance > 1.0:
            tail_penalty = 0.90

    # -------------------------------------------------------------
    # 5. Multiplicador Semântico da IA (M_IA)
    # -------------------------------------------------------------
    if adj_clean == "BOOST" and m_val <= 1.0:
        ai_mult = 1.25
    elif adj_clean == "CAUTION" and m_val >= 1.0:
        ai_mult = 0.70
    else:
        ai_mult = max(0.40, min(1.40, m_val))

    # -------------------------------------------------------------
    # 6. Produto Híbrido, Clamping e Discretização
    # -------------------------------------------------------------
    raw_units = base_units * tail_penalty * ai_mult * high_ev_haircut

    # Clamp operacional: Mínimo 0.50u, Máximo 2.50u
    clamped = max(0.50, min(2.50, raw_units))

    # Discretizar para múltiplos exatos de 0.25u
    final_units = round(clamped * 4) / 4

    # Montar justificativa formatada
    mult_pct = int(round((ai_mult - 1.0) * 100))
    mult_sign = f"+{mult_pct}%" if mult_pct > 0 else (f"{mult_pct}%" if mult_pct < 0 else "Neutro")
    haircut_note = " (Haircut prudencial 0.75x para EV > 8%)" if high_ev_haircut < 1.0 else ""
    
    rationale = ai_sizing_rationale or f"Alocação base {base_units:.2f}u com ajuste IA de {mult_sign}{haircut_note}."

    return {
        "final_units": float(final_units),
        "base_units": float(round(base_units, 2)),
        "tail_penalty": float(round(tail_penalty, 2)),
        "high_ev_haircut": float(round(high_ev_haircut, 2)),
        "ai_multiplier": float(round(ai_mult, 2)),
        "recommendation_adjustment": adj_clean,
        "sizing_rationale": rationale,
        "status": "APPROVED"
    }


def compute_portfolio_exposure_and_stats(bets_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calcula métricas agregadas da carteira inteligente:
    - total_units_staked
    - avg_stake
    - stake_distribution (0.5u, 0.75u, 1.0u, 1.25-1.5u, 1.75u+)
    - highest_conviction_pick
    """
    if not bets_list:
        return {
            "total_units_staked": 0.0,
            "avg_stake": 0.0,
            "approved_bets_count": 0,
            "vetoed_count": 0,
            "distribution": {"0.5u": 0, "0.75u": 0, "1.0u": 0, "1.25u-1.5u": 0, "1.75u+": 0},
            "highest_conviction_pick": None
        }

    total_units = sum(float(b.get("units", 1.0)) for b in bets_list)
    total_count = len(bets_list)
    avg_stake = round(total_units / total_count, 2) if total_count > 0 else 0.0

    dist = {
        "0.5u": 0,
        "0.75u": 0,
        "1.0u": 0,
        "1.25u-1.5u": 0,
        "1.75u+": 0
    }

    highest_pick = None
    max_u = -1.0

    for b in bets_list:
        u = float(b.get("units", 1.0))
        if u <= 0.60:
            dist["0.5u"] += 1
        elif u <= 0.85:
            dist["0.75u"] += 1
        elif u <= 1.10:
            dist["1.0u"] += 1
        elif u <= 1.60:
            dist["1.25u-1.5u"] += 1
        else:
            dist["1.75u+"] += 1

        if u > max_u:
            max_u = u
            highest_pick = {
                "player_name": b.get("player_name"),
                "market": b.get("market"),
                "side": b.get("side"),
                "line": b.get("line"),
                "units": u,
                "ev_percent": b.get("ev_percent"),
                "rationale": b.get("ai_sizing_rationale") or b.get("notes")
            }

    return {
        "total_units_staked": round(total_units, 2),
        "avg_stake": avg_stake,
        "approved_bets_count": total_count,
        "distribution": dist,
        "highest_conviction_pick": highest_pick
    }
