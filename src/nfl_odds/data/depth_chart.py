import os
from pathlib import Path
from typing import Optional
import polars as pl

DEFAULT_DEPTH_CHART_PATH = "data/depth_charts_2026_2027/nfl_offensive_depth_charts_2026_2027.csv"

def load_depth_chart(csv_path: str = DEFAULT_DEPTH_CHART_PATH) -> pl.DataFrame:
    """
    Carrega e normaliza o depth chart ofensivo da NFL.
    Gera colunas informativas de posição, titularidade, experiência e resumo.
    """
    if not os.path.exists(csv_path):
        print(f"Warning: Depth chart file not found at {csv_path}")
        return pl.DataFrame()
        
    df = pl.read_csv(csv_path)
    df = df.filter(pl.col("espn_id").is_not_null())
    df = df.with_columns(pl.col("espn_id").cast(pl.Int64, strict=False))
    
    rows = []
    for row in df.iter_rows(named=True):
        code = str(row.get("position_code") or "").strip()
        d_str = row.get("depth_string") or 1
        p_rank = row.get("pos_rank") or 1
        p_title = str(row.get("position_title") or "").strip()
        exp = row.get("years_exp")
        
        # Determinar sigla de posição no depth chart (ex: RB1, RB2, WR1, WR2, WR3, QB1, TE1)
        if code in ["QB", "RB", "TE", "FB"]:
            short_pos = f"{code}{d_str}"
        elif code in ["WR1", "WR2", "WR3"]:
            short_pos = code if d_str == 1 else f"{code}-D{d_str}"
        else:
            short_pos = f"{code}{d_str}"
            
        is_starter = (d_str == 1)
        role = "Titular" if is_starter else f"Reserva (#{d_str})"
        
        if exp is None:
            exp_desc = "Experiência N/A"
            years_val = None
        elif exp == 0 or exp == 0.0:
            exp_desc = "Rookie (Ano 1)"
            years_val = 0.0
        else:
            years_val = float(exp)
            exp_desc = f"{int(exp)} anos de exp"
            
        jersey = None
        if row.get("jersey_number") is not None:
            try:
                jersey = int(float(row["jersey_number"]))
            except (ValueError, TypeError):
                jersey = None
                
        college = row.get("college")
        full_name = row.get("player_name")
        team = row.get("team")
        
        rows.append({
            "espn_id": row["espn_id"],
            "depth_chart_pos": short_pos,
            "depth_role": role,
            "depth_status": "Titular" if is_starter else "Reserva / Rotação",
            "position_title": p_title,
            "pos_rank": p_rank,
            "depth_string": d_str,
            "years_exp": years_val,
            "exp_desc": exp_desc,
            "jersey_number": jersey,
            "college": college,
            "full_player_name": full_name,
            "depth_summary": f"{short_pos} ({p_title}) • {role} • {exp_desc}"
        })
        
    return pl.DataFrame(rows)

def enrich_with_depth_chart(df: pl.DataFrame, csv_path: str = DEFAULT_DEPTH_CHART_PATH) -> pl.DataFrame:
    """
    Enriquece um DataFrame (como live_value_bets) com as informações do depth chart.
    O casamento é feito preferencialmente por espn_id.
    """
    if df.is_empty():
        return df
        
    df_dc = load_depth_chart(csv_path)
    if df_dc.is_empty():
        return df
        
    if "espn_id" in df.columns:
        df_prepared = df.with_columns(pl.col("espn_id").cast(pl.Int64, strict=False))
        df_dc_unique = df_dc.unique(subset=["espn_id"])
        
        existing_dc_cols = [c for c in df_dc_unique.columns if c != "espn_id" and c in df_prepared.columns]
        if existing_dc_cols:
            df_prepared = df_prepared.drop(existing_dc_cols)
            
        enriched = df_prepared.join(df_dc_unique, on="espn_id", how="left")
        return enriched
        
    return df
