import os
os.environ.setdefault("POLARS_MAX_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("MALLOC_ARENA_MAX", "2")

import sys
import asyncio
import subprocess
import httpx
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from pydantic import BaseModel
import polars as pl
import pandas as pd
import numpy as np
import math
import json
import ctypes
import gc

from nfl_odds.betting.ev_calc import calculate_implied_probability, calculate_ev, calculate_edge
from nfl_odds.features.defense_rankings import compute_defense_rankings, get_team_defense_profile
from nfl_odds.dashboard.auth import (
    is_request_admin,
    verify_credentials,
    create_admin_token,
    get_auth_config,
    get_mfa_secret,
)

app = FastAPI(title="NFL Player Prop Analytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Segurança: Modo Somente Leitura para demonstração pública (Cloudflare / Visitantes)
READ_ONLY_MODE = os.getenv("READ_ONLY_MODE", "true").lower() in ("true", "1", "yes")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PROTECTED_PREFIXES = (
    "/api/portfolio/add",
    "/api/portfolio/import",
    "/api/portfolio/settle",
    "/api/portfolio/simulate",
    "/api/portfolio/reset",
    "/api/portfolio/clear",
    "/api/portfolio",
    "/api/run-pipeline",
    "/api/trigger-workflow",
)

class LoginRequest(BaseModel):
    password: str
    totp_code: Optional[str] = None

class SystemModeRequest(BaseModel):
    read_only: bool
    admin_secret: Optional[str] = None

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "nfl-odds-api", "timestamp": datetime.now().isoformat()}

@app.get("/api/auth/status")
def auth_status(request: Request):
    is_admin = is_request_admin(request)
    cfg = get_auth_config()
    return {
        "is_admin": is_admin,
        "mfa_enabled": cfg["mfa_enabled"],
        "read_only": READ_ONLY_MODE and not is_admin
    }

@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    if not verify_credentials(req.password, req.totp_code):
        detail_msg = "Credenciais incorretas."
        if get_mfa_secret():
            detail_msg = "Senha incorreta ou código do aplicativo autenticador (MFA) inválido."
        raise HTTPException(status_code=401, detail=detail_msg)
    
    token = create_admin_token()
    response = JSONResponse(content={
        "status": "success",
        "token": token,
        "is_admin": True,
        "message": "Autenticado com sucesso como Administrador."
    })
    response.set_cookie(
        key="nfl_admin_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=24 * 3600
    )
    return response

@app.post("/api/auth/logout")
def auth_logout():
    response = JSONResponse(content={"status": "success", "is_admin": False})
    response.delete_cookie("nfl_admin_token")
    return response

@app.get("/api/system/mode")
def get_system_mode(request: Request):
    is_admin = is_request_admin(request)
    return {
        "read_only": READ_ONLY_MODE and not is_admin,
        "has_admin_secret": bool(ADMIN_SECRET or os.getenv("ADMIN_PASSWORD")),
        "is_admin": is_admin
    }

@app.post("/api/system/mode")
def set_system_mode(req: SystemModeRequest, request: Request):
    global READ_ONLY_MODE
    if not is_request_admin(request):
        if ADMIN_SECRET and req.admin_secret != ADMIN_SECRET:
            raise HTTPException(status_code=403, detail="Chave de administrador incorreta ou sessão não autenticada.")
    READ_ONLY_MODE = req.read_only
    return {
        "status": "success",
        "read_only": READ_ONLY_MODE,
        "message": f"Modo alterado para {'Somente Leitura (Visitante)' if READ_ONLY_MODE else 'Administrador (Edição Ativa)'}."
    }

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    exempt_paths = (
        "/api/health",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/status",
        "/api/predict",
        "/docs",
        "/openapi.json",
        "/redoc",
    )
    path = request.url.path
    if path in exempt_paths:
        return await call_next(request)

    if request.method in MUTATING_METHODS:
        is_protected = any(path.startswith(p) for p in PROTECTED_PREFIXES) or path == "/api/run-pipeline"
        if is_protected:
            if not is_request_admin(request):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "🔒 Ação restrita ao Administrador: Faça login com seu autenticador MFA para atualizar odds, rodar scraping ou alterar o portfólio."
                    }
                )
    return await call_next(request)

@app.middleware("http")
async def cache_control_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# C-level memory trimming to prevent glibc heap fragmentation in Linux containers
try:
    _libc = ctypes.CDLL("libc.so.6")
except Exception:
    _libc = None

def trim_memory():
    """Forces garbage collection and releases glibc arena pages back to the OS."""
    gc.collect()
    if _libc and hasattr(_libc, "malloc_trim"):
        try:
            _libc.malloc_trim(0)
        except Exception:
            pass

_request_counter = 0

@app.middleware("http")
async def memory_management_middleware(request: Request, call_next):
    global _request_counter
    response = await call_next(request)
    _request_counter += 1
    if _request_counter % 25 == 0:
        trim_memory()
    return response

# Lazy-loaded model cache to avoid 150MB+ XGBoost/scikit-learn startup RAM overhead
_models = {}

def get_available_models() -> List[str]:
    """Returns list of models available on disk or in memory."""
    available = set(_models.keys())
    for m in ["rushing_yards", "receiving_yards", "passing_yards"]:
        if os.path.exists(f"data/{m}_model.joblib"):
            available.add(m)
    return sorted(list(available))

def get_model(market: str):
    """Lazily load a model only when requested to save RAM on startup."""
    global _models
    if market in _models:
        return _models[market]
    
    path = f"data/{market}_model.joblib"
    if not os.path.exists(path):
        return None
        
    try:
        from nfl_odds.models.train import PlayerPropModel
        model = PlayerPropModel.load(path)
        _models[market] = model
        trim_memory()
        return model
    except Exception as e:
        print(f"Error loading {market} model: {e}")
        return None

# For backwards compatibility with any external introspection
models = _models

# Zero-overhead lightweight data loaders and caches to stay under 512MB RAM
_live_bets_cache = {"mtime": 0.0, "df": pd.DataFrame(), "records": []}

def get_live_bets_df(force: bool = False) -> pd.DataFrame:
    global _live_bets_cache
    path = "data/live_value_bets.parquet"
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        mtime = os.path.getmtime(path)
        if not force and mtime == _live_bets_cache["mtime"] and not _live_bets_cache["df"].empty:
            return _live_bets_cache["df"]
        df = pl.read_parquet(path).to_pandas()
        if "ev_percent" in df.columns:
            df = df.sort_values(by="ev_percent", ascending=False)
        df = df.replace([np.inf, -np.inf], None)
        df = df.where(pd.notnull(df), None)
        _live_bets_cache["mtime"] = mtime
        _live_bets_cache["df"] = df
        _live_bets_cache["records"] = df.to_dict(orient="records")
        return df
    except Exception as e:
        print(f"Error loading live bets: {e}")
        return _live_bets_cache["df"]

def is_live_features_available() -> bool:
    return os.path.exists("data/live_features.parquet") and os.path.getsize("data/live_features.parquet") > 0

_players_cache = {"mtime": 0.0, "all": [], "by_market": {}}

def get_cached_players(market: Optional[str] = None) -> List[dict]:
    global _players_cache
    path = "data/live_features.parquet"
    if not os.path.exists(path):
        return []
    try:
        mtime = os.path.getmtime(path)
        if mtime != _players_cache["mtime"] or not _players_cache["all"]:
            lf = pl.scan_parquet(path)
            schema = lf.collect_schema()
            cols = ["player_name", "position", "team"]
            if "player_display_name" in schema:
                cols.append("player_display_name")
            if "opponent_team" in schema:
                cols.append("opponent_team")
            
            latest_season = lf.select(pl.col("season").max()).collect()[0, 0]
            latest_week = lf.filter(pl.col("season") == latest_season).select(pl.col("week").max()).collect()[0, 0]
            min_week = max(1, (latest_week or 1) - 4)
            
            df_latest = lf.filter((pl.col("season") == latest_season) & (pl.col("week") >= min_week))
            players_df = df_latest.select([c for c in cols if c in schema]).unique().collect()
            
            if "player_display_name" in players_df.columns:
                players_df = players_df.sort("player_display_name")
            else:
                players_df = players_df.sort("player_name")
                
            records = players_df.to_dicts()
            _players_cache["mtime"] = mtime
            _players_cache["all"] = records
            _players_cache["by_market"] = {}
            
        if not market:
            return _players_cache["all"]
            
        if market not in _players_cache["by_market"]:
            pos_map = {
                "passing_yards": {"QB"},
                "rushing_yards": {"RB", "QB", "WR", "FB"},
                "receiving_yards": {"WR", "TE", "RB"}
            }
            allowed = pos_map.get(market)
            if allowed:
                _players_cache["by_market"][market] = [
                    p for p in _players_cache["all"] if p.get("position") in allowed
                ]
            else:
                _players_cache["by_market"][market] = _players_cache["all"]
                
        return _players_cache["by_market"][market]
    except Exception as e:
        print(f"Error loading players cache: {e}")
        return _players_cache["all"]

def query_live_player(player_name: str, espn_id: Optional[str] = None) -> pl.DataFrame:
    path = "data/live_features.parquet"
    if not os.path.exists(path):
        return pl.DataFrame()
    try:
        lf = pl.scan_parquet(path)
        schema = lf.collect_schema()
        if espn_id and str(espn_id) not in ("undefined", "null", "") and "espn_id" in schema:
            res = lf.filter(pl.col("espn_id").cast(pl.Utf8) == str(espn_id)).collect()
            if not res.is_empty():
                return res
        clean_name = player_name.strip()
        has_display = "player_display_name" in schema
        filt = (pl.col("player_name") == clean_name) | (pl.col("player_name").str.to_lowercase() == clean_name.lower())
        if has_display:
            filt = filt | (pl.col("player_display_name") == clean_name) | (pl.col("player_display_name").str.to_lowercase() == clean_name.lower())
        return lf.filter(filt).collect()
    except Exception as e:
        print(f"Error querying live player: {e}")
        return pl.DataFrame()

def query_team_defense(opp_code: str, features: Optional[List[str]] = None, season: Optional[int] = None) -> pl.DataFrame:
    path = "data/live_features.parquet"
    if not os.path.exists(path):
        return pl.DataFrame()
    try:
        opp_code = opp_code.upper().strip()
        lf = pl.scan_parquet(path)
        schema = lf.collect_schema()
        cols = ["opponent_team", "team", "week", "season"]
        if features:
            cols += [f for f in features if f in schema and f not in cols]
            lf = lf.select(cols)
        filt = (pl.col("opponent_team") == opp_code) | (pl.col("team") == opp_code)
        if season is not None:
            filt = filt & (pl.col("season") == season)
        return lf.filter(filt).collect()
    except Exception as e:
        print(f"Error querying team defense: {e}")
        return pl.DataFrame()

# Compatibility dummy references
df_live = pl.DataFrame()
df_live_bets = pd.DataFrame()

# Warm-up lightweight caches at boot
get_live_bets_df()
get_cached_players()

NFL_TEAMS = [
    {"code": "ARI", "name": "Arizona Cardinals"},
    {"code": "ATL", "name": "Atlanta Falcons"},
    {"code": "BAL", "name": "Baltimore Ravens"},
    {"code": "BUF", "name": "Buffalo Bills"},
    {"code": "CAR", "name": "Carolina Panthers"},
    {"code": "CHI", "name": "Chicago Bears"},
    {"code": "CIN", "name": "Cincinnati Bengals"},
    {"code": "CLE", "name": "Cleveland Browns"},
    {"code": "DAL", "name": "Dallas Cowboys"},
    {"code": "DEN", "name": "Denver Broncos"},
    {"code": "DET", "name": "Detroit Lions"},
    {"code": "GB", "name": "Green Bay Packers"},
    {"code": "HOU", "name": "Houston Texans"},
    {"code": "IND", "name": "Indianapolis Colts"},
    {"code": "JAX", "name": "Jacksonville Jaguars"},
    {"code": "KC", "name": "Kansas City Chiefs"},
    {"code": "LV", "name": "Las Vegas Raiders"},
    {"code": "LAC", "name": "Los Angeles Chargers"},
    {"code": "LAR", "name": "Los Angeles Rams"},
    {"code": "MIA", "name": "Miami Dolphins"},
    {"code": "MIN", "name": "Minnesota Vikings"},
    {"code": "NE", "name": "New England Patriots"},
    {"code": "NO", "name": "New Orleans Saints"},
    {"code": "NYG", "name": "New York Giants"},
    {"code": "NYJ", "name": "New York Jets"},
    {"code": "PHI", "name": "Philadelphia Eagles"},
    {"code": "PIT", "name": "Pittsburgh Steelers"},
    {"code": "SF", "name": "San Francisco 49ers"},
    {"code": "SEA", "name": "Seattle Seahawks"},
    {"code": "TB", "name": "Tampa Bay Buccaneers"},
    {"code": "TEN", "name": "Tennessee Titans"},
    {"code": "WAS", "name": "Washington Commanders"},
]

@app.get("/api/teams")
def get_teams():
    return NFL_TEAMS

@app.get("/api/status")
def status():
    bets_df = get_live_bets_df()
    return {
        "models_loaded": get_available_models(),
        "live_data_loaded": is_live_features_available(),
        "live_bets_loaded": not bets_df.empty,
        "read_only": READ_ONLY_MODE
    }

@app.get("/api/players")
def get_players(market: str = None):
    return get_cached_players(market)

@app.get("/api/players/{player_name}/features")
def get_player_features(
    player_name: str, 
    market: str = None, 
    espn_id: str = None, 
    opponent: str = None,
    side: str = None,
    season: Optional[int] = None,
    week: Optional[int] = None
):
    if not is_live_features_available():
        raise HTTPException(status_code=400, detail="Data not loaded")
    
    player_data_all = query_live_player(player_name, espn_id=espn_id)
    if player_data_all.is_empty():
        raise HTTPException(status_code=404, detail="Player not found")
        
    # Priorizar a temporada solicitada se existir nos dados do jogador, senão a temporada mais recente
    if season is not None and season in player_data_all["season"].to_list():
        target_season = season
        season_data = player_data_all.filter(pl.col("season") == target_season)
    else:
        target_season = int(player_data_all["season"].max())
        season_data = player_data_all.filter(pl.col("season") == target_season)
        
    # Dentro da temporada resolvida, priorizar a semana solicitada ou a última semana disponível
    if week is not None and week in season_data["week"].to_list():
        target_week = week
        player_data = season_data.filter(pl.col("week") == target_week)
    else:
        target_week = int(season_data["week"].max())
        player_data = season_data.filter(pl.col("week") == target_week)
    
    # Position fallback if multiple players share the name
    if len(player_data) > 1 and market:
        if market == "passing_yards":
            player_data = player_data.filter(pl.col("position") == "QB")
        elif market == "rushing_yards":
            player_data = player_data.filter(pl.col("position").is_in(["RB", "QB", "WR", "FB"]))
        elif market == "receiving_yards":
            player_data = player_data.filter(pl.col("position").is_in(["WR", "TE", "RB"]))
        if player_data.is_empty():
            player_data = season_data.filter(pl.col("week") == target_week)
    if len(player_data) > 1:
        player_data = player_data.head(1)
        
    features_to_return = []
    importances = {}
    
    if market:
        m = get_model(market)
        if m is not None:
            features_to_return = m.features
            importances = m.get_feature_importances()
        else:
            features_to_return = ["offense_pct_avg_5"]
    else:
        # Fallback if no market
        features_to_return = ["offense_pct_avg_5"]

    # If opponent override is requested, swap defense features
    active_opponent = player_data["opponent_team"][0] if "opponent_team" in player_data.columns else None
    if opponent and opponent.strip():
        opp_code = opponent.upper().strip()
        if opp_code != active_opponent:
            def_features = [c for c in features_to_return if c.startswith("def_") or "opp" in c]
            opp_rows = query_team_defense(opp_code, def_features, season=target_season)
            if opp_rows.is_empty():
                opp_rows = query_team_defense(opp_code, def_features)
            if not opp_rows.is_empty():
                opp_season_max = opp_rows["season"].max()
                opp_season_rows = opp_rows.filter(pl.col("season") == opp_season_max)
                latest_opp_week = opp_season_rows["week"].max()
                opp_def_data = opp_season_rows.filter(pl.col("week") == latest_opp_week).head(1)
                for c in def_features:
                    if c in opp_def_data.columns and c in player_data.columns:
                        val = opp_def_data[c][0]
                        if val is not None:
                            player_data = player_data.with_columns(pl.lit(val).alias(c))
                active_opponent = opp_code

    # Obter perfil detalhado da defesa adversária com rankings da liga (Rodada 1 = 2025; Rodada 2+ = 2026)
    opp_profile = None
    if active_opponent:
        try:
            active_week = week or get_current_nfl_week(season=target_season)
            opp_profile = get_team_defense_profile(
                active_opponent, 
                season=target_season, 
                week=active_week, 
                market=market, 
                side=side
            )
        except Exception as e:
            print(f"Error computing defense profile for {active_opponent}: {e}")
            
    stats_dict = {}
    for f in features_to_return:
        if f in player_data.columns:
            val = player_data[f][0]
            # Fallback para métricas bayesianas estabilizadas se estiverem zeradas e a métrica base existir
            if f.endswith("_shrunk_season_avg"):
                base_f = f.replace("_shrunk_season_avg", "_season_avg")
                if (val is None or val == 0.0) and base_f in player_data.columns:
                    base_val = player_data[base_f][0]
                    if base_val is not None and base_val != 0.0:
                        val = base_val

            if isinstance(val, (np.floating, float)):
                stats_dict[f] = {"value": None if math.isnan(val) else float(val)}
            elif isinstance(val, (np.integer, int)):
                stats_dict[f] = {"value": int(val)}
            else:
                stats_dict[f] = {"value": val}
                
            if f in importances:
                stats_dict[f]["importance"] = importances[f]

            # Enriquecer métrica defensiva com ranking na liga, média e tier
            if opp_profile and "metrics" in opp_profile and f in opp_profile["metrics"]:
                m_info = opp_profile["metrics"][f]
                stats_dict[f]["rank"] = m_info.get("rank")
                stats_dict[f]["total_teams"] = m_info.get("total_teams")
                stats_dict[f]["league_avg"] = m_info.get("league_avg")
                stats_dict[f]["pct_diff_league"] = m_info.get("pct_diff_league")
                stats_dict[f]["tier"] = m_info.get("tier")
                stats_dict[f]["tier_label"] = m_info.get("tier_label")
                stats_dict[f]["badge_type"] = m_info.get("badge_type")
                stats_dict[f]["unit"] = m_info.get("unit")
                stats_dict[f]["higher_is_better_defense"] = m_info.get("higher_is_better_defense")
                stats_dict[f]["season_source"] = opp_profile.get("season_source")
            
    # Sort by importance
    sorted_stats = dict(sorted(
        stats_dict.items(),
        key=lambda item: item[1].get("importance", 0) if isinstance(item[1], dict) else 0,
        reverse=True
    ))

    # Anexar resumo geral do adversário
    if opp_profile:
        sorted_stats["_opponent_profile"] = opp_profile
    
    return sorted_stats

@app.get("/api/teams/{team_code}/defense-ranking")
def get_team_defense_endpoint(
    team_code: str, 
    season: int = 2026, 
    week: int = 1, 
    market: str = None, 
    side: str = None
):
    profile = get_team_defense_profile(team_code, season=season, week=week, market=market, side=side)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Defesa da equipe '{team_code}' não encontrada.")
    return profile

@app.get("/api/defense-rankings")
def get_league_defense_rankings(season: int = 2026, week: int = 3):
    return compute_defense_rankings(season=season, week=week)

class PredictRequest(BaseModel):
    player_name: str = ""
    line: float = 0.0
    odds_over: float = 0.0
    odds_under: float = 0.0
    market: str = "rushing_yards"
    stake: float = 100.0
    manual_prob_over: float = None
    opponent: str = None

@app.post("/api/predict")
def predict(req: PredictRequest):
    prob_over = 0.0
    prob_under = 0.0
    projected_yards = None
    stake = req.stake if req.stake > 0 else 100.0
    active_opponent = req.opponent
    team_name = None
    
    if req.manual_prob_over is not None:
        p = float(req.manual_prob_over)
        prob_over = p / 100.0 if p > 1.0 else p
        prob_over = max(0.001, min(0.999, prob_over))
        prob_under = 1.0 - prob_over
    else:
        if not is_live_features_available():
            raise HTTPException(status_code=400, detail="Data not loaded")
        
        model_to_use = get_model(req.market)
        if model_to_use is None:
            raise HTTPException(status_code=400, detail=f"Model for {req.market} not loaded")
            
        player_data_all = query_live_player(req.player_name)
        if player_data_all.is_empty():
            raise HTTPException(status_code=404, detail=f"Player '{req.player_name}' not found")
            
        target_season = int(player_data_all["season"].max())
        season_data = player_data_all.filter(pl.col("season") == target_season)
        latest_week = int(season_data["week"].max())
        player_data = season_data.filter(pl.col("week") == latest_week)
        
        if len(player_data) > 1:
            if req.market == "passing_yards":
                filtered = player_data.filter(pl.col("position") == "QB")
            elif req.market == "rushing_yards":
                filtered = player_data.filter(pl.col("position").is_in(["RB", "QB", "WR", "FB"]))
            elif req.market == "receiving_yards":
                filtered = player_data.filter(pl.col("position").is_in(["WR", "TE", "RB"]))
            if not filtered.is_empty():
                player_data = filtered
            player_data = player_data.head(1)
            
        team_name = player_data["team"][0] if "team" in player_data.columns else None
        active_opponent = player_data["opponent_team"][0] if "opponent_team" in player_data.columns else None

        # If custom opponent specified, dynamically swap defensive metrics
        if req.opponent and req.opponent.strip():
            opp_code = req.opponent.upper().strip()
            if opp_code != active_opponent:
                def_features = [c for c in model_to_use.features if c.startswith("def_") or "opp" in c]
                opp_rows = query_team_defense(opp_code, def_features, season=target_season)
                if opp_rows.is_empty():
                    opp_rows = query_team_defense(opp_code, def_features)
                if not opp_rows.is_empty():
                    opp_season_max = opp_rows["season"].max()
                    opp_season_rows = opp_rows.filter(pl.col("season") == opp_season_max)
                    latest_opp_week = opp_season_rows["week"].max()
                    opp_def_data = opp_season_rows.filter(pl.col("week") == latest_opp_week).head(1)
                    for c in def_features:
                        if c in opp_def_data.columns and c in player_data.columns:
                            val = opp_def_data[c][0]
                            if val is not None:
                                player_data = player_data.with_columns(pl.lit(val).alias(c))
                    active_opponent = opp_code
            
        lines_arr = np.array([req.line])
        prob_over = float(model_to_use.probability_over_line(player_data, lines_arr, calibrate=True)[0])
        prob_over = max(0.0001, min(0.9999, prob_over))
        prob_under = 1.0 - prob_over
        
        try:
            preds = model_to_use.predict_distribution(player_data)[0]
            projected_yards = float(preds[len(preds) // 2])
        except Exception:
            projected_yards = None

    implied_over = float(calculate_implied_probability(req.odds_over)) if req.odds_over > 0 else 0.0
    implied_under = float(calculate_implied_probability(req.odds_under)) if req.odds_under > 0 else 0.0
    
    edge_over = (prob_over - implied_over) * 100.0 if implied_over > 0 else 0.0
    edge_under = (prob_under - implied_under) * 100.0 if implied_under > 0 else 0.0
    
    ev_percent_over = ((prob_over * req.odds_over) - 1.0) * 100.0 if req.odds_over > 0 else 0.0
    ev_percent_under = ((prob_under * req.odds_under) - 1.0) * 100.0 if req.odds_under > 0 else 0.0
    
    profit_over = (ev_percent_over / 100.0) * stake
    profit_under = (ev_percent_under / 100.0) * stake
    
    fair_odds_over = round(min(10000.0, 1.0 / max(prob_over, 0.0001)), 2)
    fair_odds_under = round(min(10000.0, 1.0 / max(prob_under, 0.0001)), 2)
    
    def calc_kelly(p, o):
        if o <= 1.0 or p <= 0.0:
            return 0.0
        b = o - 1.0
        q = 1.0 - p
        k = (b * p - q) / b
        return max(0.0, float(k * 100.0))
        
    kelly_over = calc_kelly(prob_over, req.odds_over)
    kelly_under = calc_kelly(prob_under, req.odds_under)

    return {
        "projected_yards": round(projected_yards, 1) if projected_yards is not None else None,
        "stake": stake,
        "team": team_name,
        "opponent": active_opponent,
        "over": {
            "model_prob": prob_over,
            "implied_prob": implied_over,
            "fair_odds": round(fair_odds_over, 2),
            "edge": round(edge_over, 2),
            "ev": round(ev_percent_over, 2),
            "profit": round(profit_over, 2),
            "kelly_percent": round(kelly_over, 2),
            "half_kelly_percent": round(kelly_over / 2.0, 2),
            "recommended_stake": round((kelly_over / 200.0) * stake, 2)
        },
        "under": {
            "model_prob": prob_under,
            "implied_prob": implied_under,
            "fair_odds": round(fair_odds_under, 2),
            "edge": round(edge_under, 2),
            "ev": round(ev_percent_under, 2),
            "profit": round(profit_under, 2),
            "kelly_percent": round(kelly_under, 2),
            "half_kelly_percent": round(kelly_under / 2.0, 2),
            "recommended_stake": round((kelly_under / 200.0) * stake, 2)
        }
    }

schedule_cache = {}

def get_current_nfl_week(season: int = 2026) -> int:
    """
    Detecta a semana ativa da NFL.
    1. Se houver live_value_bets.parquet com 'week', usa a semana das apostas ao vivo.
    2. Caso contrário, consulta o calendário da temporada e identifica a menor semana com jogos futuros ou em andamento.
    """
    try:
        if os.path.exists("data/live_value_bets.parquet"):
            df = pl.read_parquet("data/live_value_bets.parquet")
            if "week" in df.columns and len(df) > 0:
                w_val = df["week"].max()
                if w_val is not None and int(w_val) > 0:
                    return int(w_val)
    except Exception as e:
        print(f"Erro ao detectar semana ativa de live_value_bets: {e}")

    try:
        from datetime import datetime
        sched = load_cached_schedule(season)
        today_str = datetime.now().strftime("%Y-%m-%d")
        upcoming = [r for r in sched if (r.get("gameday") and str(r["gameday"]) >= today_str) or r.get("status") in ("in_progress", "scheduled")]
        if upcoming:
            weeks = [int(r["week"]) for r in upcoming if r.get("week") is not None]
            if weeks:
                return min(weeks)
    except Exception as e:
        print(f"Erro ao detectar semana ativa pelo calendário: {e}")

    return 3

def load_cached_schedule(season: int = 2026, week: Optional[int] = None) -> List[dict]:
    schedule_file = f"data/schedule_{season}.json"
    records = []
    if os.path.exists(schedule_file):
        try:
            with open(schedule_file, "r") as f:
                records = json.load(f)
        except Exception as err:
            print(f"Error reading {schedule_file}: {err}")
            records = []
    
    if not records:
        try:
            import nflreadpy as nfl
            df = nfl.load_schedules([season])
            if isinstance(df, pd.DataFrame):
                df = pl.from_pandas(df)
            cols = ['game_id', 'season', 'week', 'home_team', 'away_team', 'stadium', 'location', 'gameday', 'gametime', 'home_score', 'away_score']
            avail_cols = [c for c in cols if c in df.columns]
            df_sched = df.select(avail_cols)
            records = df_sched.to_dicts()
            for r in records:
                r['week'] = int(r.get('week', 1))
                r['season'] = int(r.get('season', season))
                r['status'] = 'finished' if (r.get('home_score') is not None and r.get('away_score') is not None) else 'scheduled'
                r['status_detail'] = 'Final' if r.get('status') == 'finished' else None
                r['event_id'] = None
            try:
                with open(schedule_file, "w") as f:
                    json.dump(records, f, indent=2)
            except Exception:
                pass
        except Exception as e:
            print(f"Error loading schedule via nflreadpy: {e}")
            return []

    if week is not None and str(week).lower() != "all":
        try:
            w_int = int(week)
            return [r for r in records if int(r.get("week", 0)) == w_int]
        except ValueError:
            pass

    return records

@app.get("/api/current-week")
def get_current_week_endpoint(season: int = 2026):
    cw = get_current_nfl_week(season)
    df_live = get_live_bets_df()
    live_w = int(df_live["week"].iloc[0]) if (not df_live.empty and "week" in df_live.columns) else cw
    return {
        "season": season,
        "current_week": cw,
        "live_bets_week": live_w,
        "available_weeks": list(range(1, 19))
    }

@app.get("/api/schedule")
def get_schedule(season: int = 2026, week: Optional[str] = None, refresh: bool = False):
    target_week = None
    if week and week != "all":
        try:
            target_week = int(week)
        except ValueError:
            target_week = None

    records = load_cached_schedule(season)
    if not records:
        return []

    # Decide quais jogos enriquecer e retornar
    active_week = target_week if target_week is not None else get_current_nfl_week(season)

    # Enriquecer com ESPN live scoreboard para a semana relevante
    try:
        from nfl_odds.data.live_stats import fetch_espn_scoreboard, clean_team_code
        weeks_to_fetch = [active_week]
        if target_week is None and active_week != 1:
            weeks_to_fetch.append(1) # Também traz week 1 para históricos recentes se tudo for retornado

        espn_map = {}
        for w in set(weeks_to_fetch):
            espn_games = fetch_espn_scoreboard(season, w, force=refresh)
            for eg in espn_games:
                key = (clean_team_code(eg.get("away_team")), clean_team_code(eg.get("home_team")))
                espn_map[key] = eg
            
        for r in records:
            key = (clean_team_code(r.get("away_team")), clean_team_code(r.get("home_team")))
            eg = espn_map.get(key)
            if eg:
                if eg.get("home_score") is not None:
                    r["home_score"] = eg["home_score"]
                if eg.get("away_score") is not None:
                    r["away_score"] = eg["away_score"]
                r["status"] = eg.get("status", "scheduled")
                r["status_detail"] = eg.get("status_detail")
                r["event_id"] = eg.get("event_id")
            else:
                if r.get('home_score') is not None and r.get('away_score') is not None:
                    r['status'] = 'finished'
                    if not r.get('status_detail'):
                        r['status_detail'] = 'Final'
                elif not r.get('status'):
                    r['home_score'] = None
                    r['away_score'] = None
                    r['status'] = 'scheduled'
    except Exception as e:
        print(f"Erro ao enriquecer schedule com ESPN: {e}")

    if target_week is not None:
        return [r for r in records if int(r.get("week", 0)) == target_week]

    return records

@app.get("/api/games/{game_id}/boxscore")
def get_game_boxscore(game_id: str):
    from nfl_odds.data.live_stats import fetch_espn_scoreboard, fetch_espn_game_boxscore, clean_team_code
    try:
        records = load_cached_schedule(2026)
        game_matches = [g for g in records if g.get("game_id") == game_id]
        if not game_matches:
            try:
                import nflreadpy as nfl
                sched = nfl.load_schedules([2026])
                if isinstance(sched, pd.DataFrame):
                    sched = pl.from_pandas(sched)
                gm = sched.filter(pl.col("game_id") == game_id)
                if len(gm) > 0:
                    game_matches = gm.to_dicts()
            except Exception:
                pass
        if not game_matches:
            raise HTTPException(status_code=404, detail="Jogo não encontrado.")
            
        game_info = game_matches[0]
        home_team = clean_team_code(game_info.get("home_team"))
        away_team = clean_team_code(game_info.get("away_team"))
        
        home_players = []
        away_players = []
        home_score = game_info.get("home_score")
        away_score = game_info.get("away_score")
        status = "finished" if home_score is not None else "scheduled"

        # 1. Tenta carregar do ESPN Box Score em tempo real
        try:
            espn_sb = fetch_espn_scoreboard(2026, 1)
            target_eg = next(
                (eg for eg in espn_sb if clean_team_code(eg.get("away_team")) == away_team and clean_team_code(eg.get("home_team")) == home_team),
                None
            )
            if target_eg:
                if target_eg.get("home_score") is not None:
                    home_score = target_eg["home_score"]
                if target_eg.get("away_score") is not None:
                    away_score = target_eg["away_score"]
                status = target_eg.get("status", status)
                
                event_id = target_eg.get("event_id")
                if event_id:
                    bdata = fetch_espn_game_boxscore(event_id)
                    if bdata and bdata.get("athletes"):
                        for a in bdata["athletes"]:
                            p_dict = {
                                "player_id": a.get("player_id"),
                                "player_name": a.get("player_name"),
                                "player_display_name": a.get("player_display_name"),
                                "team": a.get("team"),
                                "position": a.get("position"),
                                "headshot_url": a.get("headshot_url"),
                                "completions": a.get("completions", 0),
                                "attempts": a.get("attempts", 0),
                                "passing_yards": a.get("passing_yards", 0.0),
                                "passing_tds": a.get("passing_tds", 0),
                                "passing_interceptions": a.get("passing_interceptions", 0),
                                "carries": a.get("carries", 0),
                                "rushing_yards": a.get("rushing_yards", 0.0),
                                "rushing_tds": a.get("rushing_tds", 0),
                                "receptions": a.get("receptions", 0),
                                "targets": a.get("targets", 0),
                                "receiving_yards": a.get("receiving_yards", 0.0),
                                "receiving_tds": a.get("receiving_tds", 0),
                            }
                            if a.get("team") == home_team:
                                home_players.append(p_dict)
                            elif a.get("team") == away_team:
                                away_players.append(p_dict)
        except Exception as e:
            print(f"Erro ao buscar boxscore na ESPN: {e}")

        # 2. Se ESPN não trouxe jogadores, faz fallback para nflreadpy
        if not home_players and not away_players:
            try:
                stats = nfl.load_player_stats([2026])
                if isinstance(stats, pd.DataFrame):
                    stats = pl.from_pandas(stats)
                game_stats = stats.filter(pl.col("game_id") == game_id)
                active = game_stats.filter(
                    (pl.col("passing_yards") > 0) | (pl.col("rushing_yards") > 0) | 
                    (pl.col("receiving_yards") > 0) | (pl.col("carries") > 0) | 
                    (pl.col("attempts") > 0) | (pl.col("receptions") > 0)
                )
                def format_player(row):
                    return {
                        "player_id": row.get("player_id"),
                        "player_name": row.get("player_name"),
                        "player_display_name": row.get("player_display_name"),
                        "team": clean_team_code(row.get("team")),
                        "position": row.get("position"),
                        "headshot_url": row.get("headshot_url"),
                        "completions": row.get("completions", 0),
                        "attempts": row.get("attempts", 0),
                        "passing_yards": float(row.get("passing_yards") or 0.0),
                        "passing_tds": row.get("passing_tds", 0),
                        "passing_interceptions": row.get("passing_interceptions", 0),
                        "carries": row.get("carries", 0),
                        "rushing_yards": float(row.get("rushing_yards") or 0.0),
                        "rushing_tds": row.get("rushing_tds", 0),
                        "receptions": row.get("receptions", 0),
                        "targets": row.get("targets", 0),
                        "receiving_yards": float(row.get("receiving_yards") or 0.0),
                        "receiving_tds": row.get("receiving_tds", 0),
                    }
                home_players = [format_player(r) for r in active.filter(pl.col("team") == home_team).to_dicts()]
                away_players = [format_player(r) for r in active.filter(pl.col("team") == away_team).to_dicts()]
            except Exception as e:
                print(f"Erro no fallback nflreadpy boxscore: {e}")

        # Apostas do banco para este jogo
        db = SessionLocal()
        game_bets = []
        try:
            bets = db.query(Bet).filter((Bet.team.in_([home_team, away_team])) | (Bet.game_id == game_id)).all()
            for b in bets:
                game_bets.append({
                    "id": b.id,
                    "player_name": b.player_name,
                    "team": b.team,
                    "market": b.market,
                    "line": b.line,
                    "side": b.side,
                    "odds": b.odds,
                    "actual_value": b.actual_value,
                    "result": b.result,
                    "profit_units": round(b.profit_units, 2) if b.profit_units is not None else 0.0,
                    "portfolio_type": b.portfolio_type,
                    "units": b.units
                })
        finally:
            db.close()
            
        return {
            "game_id": game_id,
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "gameday": game_info.get("gameday"),
            "gametime": game_info.get("gametime"),
            "stadium": game_info.get("stadium"),
            "status": status,
            "away_players": away_players,
            "home_players": home_players,
            "bets": game_bets
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar box score: {e}")

@app.get("/api/live-bets")
@app.get("/api/bets")
def get_live_bets(response: Response = None):
    if response:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    get_live_bets_df()
    return _live_bets_cache["records"]

@app.get("/api/top-picks")
def get_top_picks(limit: int = 10, response: Response = None):
    if response:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    df_live_bets = get_live_bets_df()
    if df_live_bets.empty:
        return []
        
    # Assegura que tem as colunas ev para ordenar
    sort_col = "ev_percent" if "ev_percent" in df_live_bets.columns else "ev_10_eur"
    
    # Filtra apenas picks com EV > 0, ordena e pega o top N
    top_picks = df_live_bets[df_live_bets[sort_col] > 0].sort_values(by=sort_col, ascending=False).head(limit)
    
    return top_picks.to_dict(orient="records")

import subprocess
import sys
from datetime import datetime
from typing import List, Optional
from nfl_odds.data.database import SessionLocal, Bet
from nfl_odds.data.collect_nfl import load_player_stats

class PortfolioAddRequest(BaseModel):
    player_name: str
    team: Optional[str] = None
    opponent: Optional[str] = None
    market: str
    line: float
    side: str
    odds: float
    units: float = 1.0
    base_units: Optional[float] = 1.0
    ai_multiplier: Optional[float] = 1.0
    ai_sizing_rationale: Optional[str] = None
    side_favorability: Optional[str] = None
    model_probability: Optional[float] = None
    implied_probability: Optional[float] = None
    edge: Optional[float] = None
    ev_percent: Optional[float] = None
    season: int = 2026
    week: int = 1
    portfolio_type: Optional[str] = "safe"
    notes: Optional[str] = None

class PortfolioManualSettleRequest(BaseModel):
    result: str # 'won', 'lost', 'push', 'pending'
    actual_value: Optional[float] = None

stats_cache_global = {}

_locked_cache = {"season": None, "ts": 0.0, "locked_game_ids": set(), "locked_team_weeks": set()}

def get_locked_games_and_teams(season: int = 2026):
    """
    Identifica jogos cujos horários de início (kickoff) já passaram ou cujos placares oficiais já foram lançados.
    Retorna locked_game_ids e locked_team_weeks (conjunto de tuplas (time, semana)).
    Qualquer aposta pertencente a esses jogos/semanas fica bloqueada contra alterações/exclusões.
    """
    import time
    now_ts = time.time()
    if _locked_cache["season"] == season and (now_ts - _locked_cache["ts"]) < 30.0:
        return _locked_cache["locked_game_ids"], _locked_cache["locked_team_weeks"]
        
    locked_game_ids = set()
    locked_team_weeks = set()
    now = datetime.now()

    # 1. ESPN Scoreboard (Tempo Real para semana ativa e recentes)
    try:
        from nfl_odds.data.live_stats import fetch_espn_scoreboard, clean_team_code
        curr_w = get_current_nfl_week(season)
        weeks_to_check = {1, curr_w}
        for w in weeks_to_check:
            espn_sb = fetch_espn_scoreboard(season=season, week=w)
            for eg in espn_sb:
                if eg.get("status") in ("finished", "in_progress") or eg.get("completed"):
                    if eg.get("game_id"):
                        locked_game_ids.add(eg["game_id"])
                    if eg.get("home_team"):
                        locked_team_weeks.add((clean_team_code(eg["home_team"]), w))
                    if eg.get("away_team"):
                        locked_team_weeks.add((clean_team_code(eg["away_team"]), w))
    except Exception as e:
        print(f"Erro ao verificar partidas bloqueadas via ESPN: {e}")

    # 2. Local schedule JSON (Fallback)
    try:
        from nfl_odds.data.live_stats import clean_team_code
        sched = load_cached_schedule(season)
        for row in sched:
            gid = row.get("game_id")
            w = int(row.get("week", 1))
            h_team = clean_team_code(row.get("home_team"))
            a_team = clean_team_code(row.get("away_team"))
            h_score = row.get("home_score")
            a_score = row.get("away_score")
            status = row.get("status")
            gameday = row.get("gameday")
            gametime = row.get("gametime")
            
            is_locked = False
            # 1. Jogo concluído com placar oficial
            if status in ("finished", "in_progress") or (h_score is not None and a_score is not None):
                is_locked = True
            # 2. Horário do kickoff já passou
            elif gameday:
                time_str = gametime if gametime else "00:00"
                try:
                    kickoff_dt = datetime.strptime(f"{gameday} {time_str}", "%Y-%m-%d %H:%M")
                    if now >= kickoff_dt:
                        is_locked = True
                except Exception:
                    pass
                    
            if is_locked:
                if gid:
                    locked_game_ids.add(str(gid))
                if h_team:
                    locked_team_weeks.add((str(h_team), w))
                if a_team:
                    locked_team_weeks.add((str(a_team), w))
    except Exception as e:
        print(f"Erro ao verificar partidas bloqueadas via schedule: {e}")
        
    _locked_cache["season"] = season
    _locked_cache["ts"] = now_ts
    _locked_cache["locked_game_ids"] = locked_game_ids
    _locked_cache["locked_team_weeks"] = locked_team_weeks
    return locked_game_ids, locked_team_weeks

class TriggerWorkflowRequest(BaseModel):
    week: Optional[int] = 3
    fast: Optional[bool] = False
    workflow_id: Optional[str] = "update_odds.yml"


def get_github_repo_info() -> tuple[str, str]:
    """Resolves owner and repository name from environment or git remote."""
    owner = os.getenv("GITHUB_REPO_OWNER")
    repo = os.getenv("GITHUB_REPO_NAME")
    if not owner or not repo:
        repo_full = os.getenv("GITHUB_REPOSITORY")
        if repo_full and "/" in repo_full:
            owner, repo = repo_full.split("/", 1)
    if not owner or not repo:
        try:
            out = subprocess.check_output(
                ["git", "config", "--get", "remote.origin.url"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if "github.com" in out:
                clean = out.split("github.com")[-1].lstrip("/:").rstrip(".git")
                if "/" in clean:
                    owner, repo = clean.split("/", 1)
        except Exception:
            pass
    return owner or "pontesjpp", repo or "nfl-odds"


def get_github_branch() -> str:
    """Resolves active git branch from environment or git status."""
    branch = os.getenv("GITHUB_BRANCH")
    if not branch:
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except Exception:
            branch = None
    return branch or "master"


@app.post("/api/trigger-workflow")
async def trigger_remote_workflow(
    request: Request,
    req: TriggerWorkflowRequest = TriggerWorkflowRequest(),
):
    # 1. Admin Authorization Guard
    if not is_request_admin(request):
        raise HTTPException(
            status_code=403,
            detail="🔒 Apenas o Administrador autenticado com MFA pode acionar a atualização remota."
        )

    # 2. Upfront GITHUB_TOKEN Validation (Returns 400 instead of 500 error)
    github_token = (
        os.getenv("GITHUB_TOKEN")
        or os.getenv("GH_PAT")
        or os.getenv("GITHUB_PAT")
    )
    if not github_token or not github_token.strip():
        raise HTTPException(
            status_code=400,
            detail="⚠️ GITHUB_TOKEN não configurado no servidor. Configure a variável de ambiente no Render com escopo 'actions:write'."
        )

    owner, repo = get_github_repo_info()
    branch = get_github_branch()
    workflow_file = req.workflow_id or "update_odds.yml"

    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_file}/dispatches"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token.strip()}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "nfl-odds-dashboard"
    }
    payload = {
        "ref": branch,
        "inputs": {
            "week": str(req.week or 2),
            "fast": "true" if req.fast else "false"
        }
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)

            if resp.status_code == 204:
                actions_url = f"https://github.com/{owner}/{repo}/actions/workflows/{workflow_file}"
                run_id = None
                run_url = actions_url

                try:
                    await asyncio.sleep(1.0)
                    runs_api = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_file}/runs?per_page=1"
                    r_runs = await client.get(runs_api, headers=headers)
                    if r_runs.status_code == 200:
                        runs_list = r_runs.json().get("workflow_runs", [])
                        if runs_list:
                            run_id = runs_list[0].get("id")
                            run_url = runs_list[0].get("html_url") or actions_url
                except Exception:
                    pass

                return {
                    "status": "success",
                    "message": f"Workflow '{workflow_file}' disparado com sucesso para a Semana {req.week} no branch '{branch}'.",
                    "run_id": run_id,
                    "run_url": run_url,
                    "actions_url": actions_url,
                    "owner": owner,
                    "repo": repo,
                    "branch": branch,
                }
            elif resp.status_code == 401:
                raise HTTPException(status_code=401, detail="Token do GitHub inválido ou expirado. Verifique GITHUB_TOKEN.")
            elif resp.status_code == 403:
                raise HTTPException(status_code=403, detail="GITHUB_TOKEN não possui permissão para disparar workflows (escopo 'actions:write' necessário).")
            elif resp.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Workflow '{workflow_file}' ou repositório '{owner}/{repo}' não encontrado no branch '{branch}'.")
            elif resp.status_code == 422:
                err_body = resp.json() if resp.text else {}
                raise HTTPException(status_code=422, detail=f"Parâmetros de workflow inválidos: {err_body.get('message', resp.text)}")
            else:
                raise HTTPException(status_code=resp.status_code, detail=f"Erro do GitHub ({resp.status_code}): {resp.text}")

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Falha de rede ao contatar a API do GitHub Actions: {e}")


@app.get("/api/workflow-status")
async def get_workflow_status(
    workflow_id: Optional[str] = "update_odds.yml",
    run_id: Optional[int] = None,
):
    github_token = (
        os.getenv("GITHUB_TOKEN")
        or os.getenv("GH_PAT")
        or os.getenv("GITHUB_PAT")
    )
    owner, repo = get_github_repo_info()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "nfl-odds-dashboard"
    }
    if github_token and github_token.strip():
        headers["Authorization"] = f"Bearer {github_token.strip()}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            if run_id:
                url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}"
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "run_id": data.get("id"),
                        "status": data.get("status"),          # 'queued', 'in_progress', 'completed'
                        "conclusion": data.get("conclusion"),  # 'success', 'failure', 'cancelled'
                        "html_url": data.get("html_url"),
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at"),
                    }
                elif resp.status_code == 404:
                    return {"status": "not_found", "message": f"Run {run_id} não encontrada."}
                else:
                    return {"status": "error", "code": resp.status_code, "message": resp.text}
            else:
                url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs?per_page=3"
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    runs = resp.json().get("workflow_runs", [])
                    if runs:
                        latest = runs[0]
                        return {
                            "run_id": latest.get("id"),
                            "status": latest.get("status"),
                            "conclusion": latest.get("conclusion"),
                            "html_url": latest.get("html_url"),
                            "created_at": latest.get("created_at"),
                            "updated_at": latest.get("updated_at"),
                        }
                    return {"status": "none", "message": "Nenhuma execução recente encontrada."}
                elif resp.status_code == 404:
                    return {"status": "not_found", "message": "Workflow ou repositório não encontrado."}
                else:
                    return {"status": "error", "code": resp.status_code, "message": resp.text}
        except Exception as e:
            return {"status": "error", "message": str(e)}


@app.post("/api/run-pipeline")
async def run_pipeline_api(request: Request):
    if not is_request_admin(request):
        raise HTTPException(
            status_code=403,
            detail="🔒 Apenas o Administrador autenticado com MFA pode atualizar odds e acionar a IA."
        )
    is_render = os.getenv("RENDER") == "true" or os.getenv("IS_RENDER") == "true"
    has_token = bool(os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT") or os.getenv("GITHUB_PAT"))

    # If running on Render or when GITHUB_TOKEN is present, auto-delegate to GitHub Actions
    if has_token:
        active_w = get_current_nfl_week()
        return await trigger_remote_workflow(request=request, req=TriggerWorkflowRequest(week=active_w, fast=False))

    if is_render:
        raise HTTPException(
            status_code=400,
            detail="⚠️ O scraper e pipeline consomem mais de 512MB de RAM e não podem ser executados diretamente no container web do Render. Configure a variável GITHUB_TOKEN no Render para acionamento remoto automático via GitHub Actions, ou execute './scripts/update_odds.sh' localmente."
        )

    try:
        # Run the scraper
        subprocess.run([sys.executable, "scripts/run_scraper.py"], check=True)
        # Run the pipeline
        subprocess.run([sys.executable, "pipeline.py", "--live"], check=True)

        # Auto-sync portfolios for pending bets so recommendations and portfolio stay 100% aligned
        try:
            import_safe_picks(replace_pending=True)
            import_high_risk_picks(replace_pending=True)
            import_all_props(replace_pending=True)
        except Exception as sync_err:
            print(f"Auto-sync warning: {sync_err}")

        return {"status": "success", "mode": "local"}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")

@app.get("/api/portfolio")
def get_portfolio(portfolio_type: str = "safe", week: Optional[str] = None, game_id: Optional[str] = None, response: Response = None):
    if response:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    db = SessionLocal()
    try:
        df_live_bets = get_live_bets_df()
        live_safe_count = 0
        live_safe_flat_count = 0
        live_high_risk_count = 0
        live_all_props_count = 0
        if not df_live_bets.empty:
            ev_col = "ev_percent" if "ev_percent" in df_live_bets.columns else "ev_10_eur"
            live_safe_count = int(((df_live_bets[ev_col] >= 2.5) & (df_live_bets[ev_col] <= 15.0)).sum())
            live_safe_flat_count = live_safe_count
            live_high_risk_count = int((df_live_bets[ev_col] > 20.0).sum())
            # All props com EV positivo estrito
            df_positive = df_live_bets[df_live_bets[ev_col] > 0.0]
            live_all_props_count = len(df_positive.drop_duplicates(subset=["player_name", "market", "line"]))

        all_bets = db.query(Bet).all()
        safe_count = sum(1 for b in all_bets if (b.portfolio_type or "safe") == "safe")
        safe_flat_count = sum(1 for b in all_bets if b.portfolio_type == "safe_flat")
        high_risk_count = sum(1 for b in all_bets if b.portfolio_type == "high_risk")
        all_props_count = sum(1 for b in all_bets if b.portfolio_type == "all_props")
        
        type_bets = [b for b in all_bets if (b.portfolio_type or "safe") == portfolio_type]
        available_weeks = sorted(list(set(b.week for b in all_bets if b.week is not None)), reverse=True)
        if not df_live_bets.empty and "week" in df_live_bets.columns:
            lw = int(df_live_bets["week"].iloc[0])
            if lw not in available_weeks:
                available_weeks = sorted(available_weeks + [lw], reverse=True)

        if week and week != "all":
            try:
                w_int = int(week)
                bets = [b for b in type_bets if b.week == w_int]
            except ValueError:
                bets = type_bets
        else:
            bets = type_bets

        if game_id and game_id != "all":
            bets = [
                b for b in bets 
                if b.game_id == game_id or (
                    b.team and b.opponent and (
                        f"_{b.team}_{b.opponent}" in game_id or f"_{b.opponent}_{b.team}" in game_id
                    )
                )
            ]

        bets.sort(key=lambda b: b.timestamp or datetime.min)
        
        total_bets = len(bets)
        settled_bets = [b for b in bets if b.result in ('won', 'lost', 'push')]
        pending_bets = [b for b in bets if b.result == 'pending']
        won_bets = [b for b in bets if b.result == 'won']
        lost_bets = [b for b in bets if b.result == 'lost']
        push_bets = [b for b in bets if b.result == 'push']
        
        total_staked_units = sum(b.units for b in bets)
        settled_staked_units = sum(b.units for b in settled_bets)
        pending_staked_units = sum(b.units for b in pending_bets)
        net_profit_units = sum(b.profit_units for b in settled_bets)
        
        roi_percent = (net_profit_units / settled_staked_units * 100.0) if settled_staked_units > 0 else 0.0
        resolved_count = len(won_bets) + len(lost_bets)
        win_rate_percent = (len(won_bets) / resolved_count * 100.0) if resolved_count > 0 else 0.0
        hit_rate_percent = (len(won_bets) / len(settled_bets) * 100.0) if len(settled_bets) > 0 else 0.0
        avg_odds = (sum(b.odds * b.units for b in bets) / total_staked_units) if total_staked_units > 0 else 0.0
        
        gross_profit = sum(b.profit_units for b in won_bets)
        gross_loss = abs(sum(b.profit_units for b in lost_bets))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
        
        # Build equity curve
        equity_curve = [{"bet_index": 0, "player": "Início", "step_units": 0.0, "cum_units": 0.0}]
        cum = 0.0
        for idx, b in enumerate(settled_bets, 1):
            cum += b.profit_units
            equity_curve.append({
                "bet_index": idx,
                "bet_id": b.id,
                "player": b.player_name,
                "market": b.market,
                "result": b.result,
                "step_units": round(b.profit_units, 2),
                "cum_units": round(cum, 2)
            })
            
        locked_game_ids, locked_team_weeks = get_locked_games_and_teams(2026)

        bets_data = []
        for b in reversed(bets):
            is_locked = bool(
                b.is_locked
                or b.result in ('won', 'lost', 'push')
                or (b.game_id and b.game_id in locked_game_ids)
                or (b.team and (b.team, b.week) in locked_team_weeks)
            )
            bets_data.append({
                "id": b.id,
                "timestamp": b.timestamp.isoformat() if b.timestamp else None,
                "season": b.season,
                "week": b.week,
                "game_id": b.game_id,
                "player_name": b.player_name,
                "team": b.team,
                "opponent": b.opponent,
                "bookmaker": b.bookmaker,
                "market": b.market,
                "line": b.line,
                "side": b.side,
                "odds": b.odds,
                "units": b.units,
                "base_units": getattr(b, "base_units", 1.0) or 1.0,
                "ai_multiplier": getattr(b, "ai_multiplier", 1.0) or 1.0,
                "ai_sizing_rationale": getattr(b, "ai_sizing_rationale", None),
                "ai_summary": getattr(b, "ai_summary", None),
                "side_favorability": getattr(b, "side_favorability", None),
                "model_probability": b.model_probability,
                "implied_probability": b.implied_probability,
                "edge": b.edge,
                "ev_percent": b.ev_percent,
                "actual_value": b.actual_value,
                "result": b.result,
                "profit_units": round(b.profit_units, 2),
                "settled_at": b.settled_at.isoformat() if b.settled_at else None,
                "portfolio_type": b.portfolio_type or "safe",
                "is_locked": is_locked,
                "notes": b.notes
            })

        from nfl_odds.betting.dynamic_sizing import compute_portfolio_exposure_and_stats
        target_stats_bets = pending_bets if len(pending_bets) > 0 else bets
        smart_stats = compute_portfolio_exposure_and_stats([
            {
                "player_name": b.player_name,
                "market": b.market,
                "side": b.side,
                "line": b.line,
                "units": b.units,
                "ev_percent": b.ev_percent,
                "ai_sizing_rationale": getattr(b, "ai_sizing_rationale", None)
            }
            for b in target_stats_bets
        ])
            
        return {
            "portfolio_type": portfolio_type,
            "read_only": READ_ONLY_MODE,
            "safe_count": safe_count,
            "safe_flat_count": safe_flat_count,
            "high_risk_count": high_risk_count,
            "all_props_count": all_props_count,
            "live_safe_count": live_safe_count,
            "live_safe_flat_count": live_safe_flat_count,
            "live_high_risk_count": live_high_risk_count,
            "live_all_props_count": live_all_props_count,
            "available_weeks": available_weeks,
            "selected_week": str(week) if week and week != "all" else "all",
            "summary": {
                "total_bets": total_bets,
                "settled_count": len(settled_bets),
                "pending_count": len(pending_bets),
                "won_count": len(won_bets),
                "lost_count": len(lost_bets),
                "push_count": len(push_bets),
                "total_staked_units": round(total_staked_units, 2),
                "settled_staked_units": round(settled_staked_units, 2),
                "pending_staked_units": round(pending_staked_units, 2),
                "net_profit_units": round(net_profit_units, 2),
                "roi_percent": round(roi_percent, 2),
                "win_rate_percent": round(win_rate_percent, 2),
                "hit_rate_percent": round(hit_rate_percent, 2),
                "resolved_count": resolved_count,
                "avg_odds": round(avg_odds, 2),
                "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
                "avg_stake_units": smart_stats["avg_stake"],
                "stake_distribution": smart_stats["distribution"],
                "highest_conviction_pick": smart_stats["highest_conviction_pick"]
            },
            "equity_curve": equity_curve,
            "bets": bets_data
        }
    finally:
        db.close()

@app.post("/api/portfolio/add")
def add_portfolio_bet(req: PortfolioAddRequest):
    locked_game_ids, locked_teams = get_locked_games_and_teams(req.season)
    if (req.team and req.team in locked_teams):
        raise HTTPException(
            status_code=400,
            detail="Não é permitido incluir apostas em partidas que já iniciaram ou foram concluídas. Aposta bloqueada."
        )
    db = SessionLocal()
    try:
        ptype = req.portfolio_type or ("high_risk" if (req.ev_percent is not None and req.ev_percent > 20.0) else "safe")
        existing = db.query(Bet).filter(
            Bet.player_name == req.player_name,
            Bet.market == req.market,
            Bet.line == req.line,
            Bet.side == req.side,
            Bet.season == req.season,
            Bet.week == req.week,
            Bet.portfolio_type == ptype
        ).first()
        
        if existing:
            return {"status": "already_exists", "bet_id": existing.id, "portfolio_type": ptype}
            
        new_bet = Bet(
            player_name=req.player_name,
            team=req.team,
            opponent=req.opponent,
            market=req.market,
            line=req.line,
            side=req.side,
            odds=req.odds,
            units=req.units or 1.0,
            base_units=req.base_units or req.units or 1.0,
            ai_multiplier=req.ai_multiplier or 1.0,
            ai_sizing_rationale=req.ai_sizing_rationale,
            side_favorability=req.side_favorability,
            model_probability=req.model_probability,
            implied_probability=req.implied_probability,
            edge=req.edge,
            ev_percent=req.ev_percent,
            season=req.season,
            week=req.week,
            result="pending",
            profit_units=0.0,
            portfolio_type=ptype,
            is_locked=False,
            notes=req.notes
        )
        db.add(new_bet)
        db.commit()
        db.refresh(new_bet)
        return {"status": "created", "bet_id": new_bet.id, "portfolio_type": ptype}
    finally:
        db.close()

@app.post("/api/portfolio/import-safe-picks")
def import_safe_picks(replace_pending: bool = False, flat_stake: bool = False, portfolio_type: str = "safe"):
    df_live_bets = get_live_bets_df(force=True)
    if df_live_bets.empty:
        return {"imported": 0, "message": "Nenhuma aposta ao vivo encontrada."}
        
    ev_col = "ev_percent" if "ev_percent" in df_live_bets.columns else "ev_10_eur"
    mask = (df_live_bets[ev_col] >= 2.5) & (df_live_bets[ev_col] <= 15.0)
    
    safe_df = df_live_bets[mask]
    target_ptype = "safe_flat" if (flat_stake or portfolio_type == "safe_flat") else "safe"
    target_week = int(safe_df["week"].iloc[0]) if ("week" in safe_df.columns and not safe_df.empty) else 1
    
    locked_game_ids, locked_team_weeks = get_locked_games_and_teams(2026)
    
    db = SessionLocal()
    imported_count = 0
    updated_count = 0
    skipped_locked_count = 0
    try:
        if replace_pending:
            del_query = db.query(Bet).filter(
                Bet.result == "pending",
                Bet.portfolio_type == target_ptype,
                Bet.week == target_week,
                Bet.is_locked == False
            )
            if locked_game_ids:
                del_query = del_query.filter(~Bet.game_id.in_(locked_game_ids))
            del_query.delete(synchronize_session=False)
            db.commit()

        for _, row in safe_df.iterrows():
            team = str(row.get("team", "")) if row.get("team") else None
            game_id = str(row.get("game_id", "")) if row.get("game_id") else None
            season = int(row.get("season", 2026))
            week = int(row.get("week", target_week))
            
            # SANITY CHECK: Nunca importar ou substituir apostas de partidas iniciadas/encerradas
            if (game_id and game_id in locked_game_ids) or (team and (team, week) in locked_team_weeks):
                skipped_locked_count += 1
                continue
                
            player_name = str(row.get("player_name", ""))
            market = str(row.get("market", ""))
            line = float(row.get("line", 0.0))
            side = str(row.get("side", "over")).lower()
            odds = float(row.get("odds", 1.85))
            season = int(row.get("season", 2026))
            week = int(row.get("week", 1))

            # Win probability
            if "prob_win" in row and row.get("prob_win") is not None:
                win_prob = float(row["prob_win"])
            elif "model_prob" in row and row.get("model_prob") is not None:
                m_p = float(row["model_prob"])
                win_prob = m_p if side == "over" else (1.0 - m_p)
            else:
                win_prob = None

            implied_p = float(row["implied_prob"]) if row.get("implied_prob") is not None else (1.0 / odds if odds > 0 else None)
            edge_v = float(row["edge"]) if row.get("edge") is not None else ((win_prob - implied_p) if (win_prob and implied_p) else None)
            ev_v = float(row[ev_col]) if row.get(ev_col) is not None else None

            from nfl_odds.betting.dynamic_sizing import calculate_smart_units

            ai_mult = float(row.get("ai_unit_multiplier")) if row.get("ai_unit_multiplier") is not None else 1.0
            rec_adj = str(row.get("recommendation_adjustment") or "MAINTAIN")
            ai_rat = str(row.get("ai_sizing_rationale") or "")
            side_fav = str(row.get("side_favorability") or "NEUTRAL")
            z_dist = float(row.get("z_distance")) if (row.get("z_distance") is not None and not pd.isna(row.get("z_distance"))) else None

            if flat_stake or target_ptype == "safe_flat":
                units_to_use = 1.0
                base_u = 1.0
                final_mult = 1.0
                rationale_to_use = "Flat Stake: 1.0 unidade fixa em todas as recomendações."
            else:
                smart = calculate_smart_units(
                    ev_percent=ev_v if ev_v is not None else 5.0,
                    odds=odds,
                    prob_win=win_prob or (1.0 / odds if odds > 0 else 0.5),
                    side=side,
                    market=market,
                    z_distance=z_dist,
                    ai_multiplier=ai_mult,
                    recommendation_adjustment=rec_adj,
                    ai_sizing_rationale=ai_rat
                )

                # Se a IA vetou formalmente (AVOID), não adiciona na carteira
                if smart["status"] == "VETOED_BY_AI" or smart["final_units"] <= 0.0:
                    continue

                units_to_use = smart["final_units"]
                base_u = smart["base_units"]
                final_mult = smart["ai_multiplier"]
                rationale_to_use = smart["sizing_rationale"]
            
            existing = db.query(Bet).filter(
                Bet.player_name == player_name,
                Bet.market == market,
                Bet.line == line,
                Bet.side == side,
                Bet.season == season,
                Bet.week == week,
                Bet.portfolio_type == target_ptype
            ).first()
            
            if not existing:
                new_bet = Bet(
                    player_name=player_name,
                    team=team,
                    opponent=str(row.get("opponent", "")) if row.get("opponent") else None,
                    game_id=game_id,
                    market=market,
                    line=line,
                    side=side,
                    odds=odds,
                    units=units_to_use,
                    base_units=base_u,
                    ai_multiplier=final_mult,
                    ai_sizing_rationale=rationale_to_use,
                    side_favorability=side_fav,
                    ai_summary=str(row.get("ai_summary", "")) if row.get("ai_summary") else None,
                    model_probability=win_prob,
                    implied_probability=implied_p,
                    edge=edge_v,
                    ev_percent=ev_v,
                    season=season,
                    week=week,
                    portfolio_type=target_ptype,
                    result="pending",
                    profit_units=0.0,
                    is_locked=False
                )
                db.add(new_bet)
                imported_count += 1
            else:
                if existing.result == "pending" and not existing.is_locked:
                    existing.odds = odds
                    existing.units = units_to_use
                    existing.base_units = base_u
                    existing.ai_multiplier = final_mult
                    existing.ai_sizing_rationale = rationale_to_use
                    existing.side_favorability = side_fav
                    existing.ai_summary = str(row.get("ai_summary", "")) if row.get("ai_summary") else None
                    existing.model_probability = win_prob
                    existing.implied_probability = implied_p
                    existing.edge = edge_v
                    existing.ev_percent = ev_v
                    updated_count += 1
                
        db.commit()
        return {
            "imported": imported_count,
            "updated": updated_count,
            "skipped_locked": skipped_locked_count,
            "total_safe_found": len(safe_df),
            "replaced": replace_pending,
            "portfolio_type": target_ptype
        }
    finally:
        db.close()

@app.post("/api/portfolio/import-safe-flat")
def import_safe_flat(replace_pending: bool = False):
    return import_safe_picks(replace_pending=replace_pending, flat_stake=True, portfolio_type="safe_flat")

@app.post("/api/portfolio/import-high-risk-picks")
def import_high_risk_picks(replace_pending: bool = False):
    df_live_bets = get_live_bets_df(force=True)
    if df_live_bets.empty:
        return {"imported": 0, "message": "Nenhuma aposta ao vivo encontrada."}
        
    ev_col = "ev_percent" if "ev_percent" in df_live_bets.columns else "ev_10_eur"
    # Regra estrita de alto risco: apenas EV > 20.0%
    mask = df_live_bets[ev_col] > 20.0
    
    hr_df = df_live_bets[mask]
    target_week = int(hr_df["week"].iloc[0]) if ("week" in hr_df.columns and not hr_df.empty) else 1
    
    locked_game_ids, locked_team_weeks = get_locked_games_and_teams(2026)
    
    db = SessionLocal()
    imported_count = 0
    updated_count = 0
    skipped_locked_count = 0
    try:
        if replace_pending:
            del_query = db.query(Bet).filter(
                Bet.result == "pending",
                Bet.portfolio_type == "high_risk",
                Bet.week == target_week,
                Bet.is_locked == False
            )
            if locked_game_ids:
                del_query = del_query.filter(~Bet.game_id.in_(locked_game_ids))
            del_query.delete(synchronize_session=False)
            db.commit()

        for _, row in hr_df.iterrows():
            team = str(row.get("team", "")) if row.get("team") else None
            game_id = str(row.get("game_id", "")) if row.get("game_id") else None
            season = int(row.get("season", 2026))
            week = int(row.get("week", target_week))
            
            # SANITY CHECK: Nunca importar ou substituir apostas de partidas iniciadas/encerradas
            if (game_id and game_id in locked_game_ids) or (team and (team, week) in locked_team_weeks):
                skipped_locked_count += 1
                continue
                
            player_name = str(row.get("player_name", ""))
            market = str(row.get("market", ""))
            line = float(row.get("line", 0.0))
            side = str(row.get("side", "over")).lower()
            odds = float(row.get("odds", 1.85))
            season = int(row.get("season", 2026))
            week = int(row.get("week", 1))

            if "prob_win" in row and row.get("prob_win") is not None:
                win_prob = float(row["prob_win"])
            elif "model_prob" in row and row.get("model_prob") is not None:
                m_p = float(row["model_prob"])
                win_prob = m_p if side == "over" else (1.0 - m_p)
            else:
                win_prob = None

            implied_p = float(row["implied_prob"]) if row.get("implied_prob") is not None else (1.0 / odds if odds > 0 else None)
            edge_v = float(row["edge"]) if row.get("edge") is not None else ((win_prob - implied_p) if (win_prob and implied_p) else None)
            ev_v = float(row[ev_col]) if row.get(ev_col) is not None else None
            
            existing = db.query(Bet).filter(
                Bet.player_name == player_name,
                Bet.market == market,
                Bet.line == line,
                Bet.side == side,
                Bet.season == season,
                Bet.week == week,
                Bet.portfolio_type == "high_risk"
            ).first()
            
            if not existing:
                new_bet = Bet(
                    player_name=player_name,
                    team=team,
                    opponent=str(row.get("opponent", "")) if row.get("opponent") else None,
                    game_id=game_id,
                    market=market,
                    line=line,
                    side=side,
                    odds=odds,
                    units=1.0,
                    ai_multiplier=float(row.get("ai_unit_multiplier", 1.0)) if row.get("ai_unit_multiplier") is not None else 1.0,
                    ai_sizing_rationale=str(row.get("ai_sizing_rationale", "")) if row.get("ai_sizing_rationale") else None,
                    side_favorability=str(row.get("side_favorability", "NEUTRAL")) if row.get("side_favorability") else None,
                    ai_summary=str(row.get("ai_summary", "")) if row.get("ai_summary") else None,
                    model_probability=win_prob,
                    implied_probability=implied_p,
                    edge=edge_v,
                    ev_percent=ev_v,
                    season=season,
                    week=week,
                    portfolio_type="high_risk",
                    result="pending",
                    profit_units=0.0,
                    is_locked=False
                )
                db.add(new_bet)
                imported_count += 1
            else:
                if existing.result == "pending" and not existing.is_locked:
                    existing.odds = odds
                    existing.model_probability = win_prob
                    existing.implied_probability = implied_p
                    existing.edge = edge_v
                    existing.ev_percent = ev_v
                    existing.ai_multiplier = float(row.get("ai_unit_multiplier", 1.0)) if row.get("ai_unit_multiplier") is not None else 1.0
                    existing.ai_sizing_rationale = str(row.get("ai_sizing_rationale", "")) if row.get("ai_sizing_rationale") else None
                    existing.side_favorability = str(row.get("side_favorability", "NEUTRAL")) if row.get("side_favorability") else None
                    existing.ai_summary = str(row.get("ai_summary", "")) if row.get("ai_summary") else None
                    updated_count += 1
                
        db.commit()
        return {
            "imported": imported_count,
            "updated": updated_count,
            "skipped_locked": skipped_locked_count,
            "total_high_risk_found": len(hr_df),
            "replaced": replace_pending
        }
    finally:
        db.close()

@app.post("/api/portfolio/import-all-props")
def import_all_props(replace_pending: bool = False, mode: str = "best_side"):
    df_live_bets = get_live_bets_df(force=True)
    if df_live_bets.empty:
        return {"imported": 0, "message": "Nenhuma aposta ao vivo encontrada."}
        
    ev_col = "ev_percent" if "ev_percent" in df_live_bets.columns else "ev_10_eur"
    
    # REGRA ESTRITA: Apenas props com EV positivo (> 0). Props com EV negativo nunca entram na carteira!
    df_positive = df_live_bets[df_live_bets[ev_col] > 0.0]
    
    if mode == "all_rows":
        target_df = df_positive
    else:
        # Padrão: Seleciona o lado mais favorável (maior EV) para cada uma das props do mercado, estritamente com EV > 0
        target_df = df_positive.sort_values(by=ev_col, ascending=False).drop_duplicates(subset=["player_name", "market", "line"])
        
    target_week = int(target_df["week"].iloc[0]) if ("week" in target_df.columns and not target_df.empty) else 1
    locked_game_ids, locked_team_weeks = get_locked_games_and_teams(2026)

    db = SessionLocal()
    imported_count = 0
    updated_count = 0
    skipped_locked_count = 0
    try:
        if replace_pending:
            # SANITY CHECK: Nunca deletar apostas de partidas iniciadas/encerradas ou com resultado!
            del_query = db.query(Bet).filter(
                Bet.result == "pending",
                Bet.portfolio_type == "all_props",
                Bet.week == target_week,
                Bet.is_locked == False
            )
            if locked_game_ids:
                del_query = del_query.filter(~Bet.game_id.in_(locked_game_ids))
            del_query.delete(synchronize_session=False)
            db.commit()

        for _, row in target_df.iterrows():
            team = str(row.get("team", "")) if row.get("team") else None
            game_id = str(row.get("game_id", "")) if row.get("game_id") else None
            season = int(row.get("season", 2026))
            week = int(row.get("week", target_week))
            
            # SANITY CHECK: Não importar novas apostas para partidas já iniciadas ou encerradas
            if (game_id and game_id in locked_game_ids) or (team and (team, week) in locked_team_weeks):
                skipped_locked_count += 1
                continue
                
            player_name = str(row.get("player_name", ""))
            market = str(row.get("market", ""))
            line = float(row.get("line", 0.0))
            side = str(row.get("side", "over")).lower()
            odds = float(row.get("odds", 1.85))
            season = int(row.get("season", 2026))
            week = int(row.get("week", 1))

            if "prob_win" in row and row.get("prob_win") is not None:
                win_prob = float(row["prob_win"])
            elif "model_prob" in row and row.get("model_prob") is not None:
                m_p = float(row["model_prob"])
                win_prob = m_p if side == "over" else (1.0 - m_p)
            else:
                win_prob = None

            implied_p = float(row["implied_prob"]) if row.get("implied_prob") is not None else (1.0 / odds if odds > 0 else None)
            edge_v = float(row["edge"]) if row.get("edge") is not None else ((win_prob - implied_p) if (win_prob and implied_p) else None)
            ev_v = float(row[ev_col]) if row.get(ev_col) is not None else None
            
            existing = db.query(Bet).filter(
                Bet.player_name == player_name,
                Bet.market == market,
                Bet.line == line,
                Bet.side == side,
                Bet.season == season,
                Bet.week == week,
                Bet.portfolio_type == "all_props"
            ).first()
            
            if not existing:
                new_bet = Bet(
                    player_name=player_name,
                    team=team,
                    opponent=str(row.get("opponent", "")) if row.get("opponent") else None,
                    game_id=game_id,
                    market=market,
                    line=line,
                    side=side,
                    odds=odds,
                    units=1.0,
                    ai_multiplier=float(row.get("ai_unit_multiplier", 1.0)) if row.get("ai_unit_multiplier") is not None else 1.0,
                    ai_sizing_rationale=str(row.get("ai_sizing_rationale", "")) if row.get("ai_sizing_rationale") else None,
                    side_favorability=str(row.get("side_favorability", "NEUTRAL")) if row.get("side_favorability") else None,
                    ai_summary=str(row.get("ai_summary", "")) if row.get("ai_summary") else None,
                    model_probability=win_prob,
                    implied_probability=implied_p,
                    edge=edge_v,
                    ev_percent=ev_v,
                    season=season,
                    week=week,
                    portfolio_type="all_props",
                    result="pending",
                    profit_units=0.0,
                    is_locked=False
                )
                db.add(new_bet)
                imported_count += 1
            else:
                # SANITY CHECK: Nunca atualizar se a aposta já foi liquidada ou bloqueada!
                if existing.result == "pending" and not existing.is_locked:
                    existing.odds = odds
                    existing.model_probability = win_prob
                    existing.implied_probability = implied_p
                    existing.edge = edge_v
                    existing.ev_percent = ev_v
                    existing.ai_multiplier = float(row.get("ai_unit_multiplier", 1.0)) if row.get("ai_unit_multiplier") is not None else 1.0
                    existing.ai_sizing_rationale = str(row.get("ai_sizing_rationale", "")) if row.get("ai_sizing_rationale") else None
                    existing.side_favorability = str(row.get("side_favorability", "NEUTRAL")) if row.get("side_favorability") else None
                    existing.ai_summary = str(row.get("ai_summary", "")) if row.get("ai_summary") else None
                    updated_count += 1
                
        db.commit()
        return {
            "imported": imported_count,
            "updated": updated_count,
            "skipped_locked": skipped_locked_count,
            "total_props_found": len(target_df),
            "mode": mode,
            "replaced": replace_pending
        }
    finally:
        db.close()

@app.post("/api/portfolio/settle")
def settle_portfolio(
    portfolio_type: Optional[str] = None, 
    game_id: Optional[str] = None, 
    re_settle_pushes: bool = True,
    re_settle_all: bool = False
):
    db = SessionLocal()
    try:
        if re_settle_all:
            results_to_check = ["pending", "push", "won", "lost"]
        else:
            results_to_check = ["pending", "push"] if re_settle_pushes else ["pending"]

        query = db.query(Bet).filter(Bet.result.in_(results_to_check))
        if portfolio_type:
            query = query.filter(Bet.portfolio_type == portfolio_type)
        if game_id:
            query = query.filter(Bet.game_id == game_id)
        candidate_bets = query.all()
        if not candidate_bets:
            return {"settled": 0, "message": "Nenhuma aposta pendente ou passível de liquidação na carteira."}

        from nfl_odds.data.live_stats import (
            get_all_finished_game_stats,
            match_player_in_stats,
            clean_team_code
        )

        # 1. Carregar catálogo completo de jogos finalizados e estatísticas oficiais (ESPN + nflreadpy) POR SEMANA
        candidate_weeks = list(set(b.week for b in candidate_bets if b.week)) or [3]
        finished_games_by_week: Dict[int, Dict[str, Any]] = {}
        players_by_week: Dict[int, List[Dict[str, Any]]] = {}
        for w in candidate_weeks:
            w_games, w_players = get_all_finished_game_stats(season=2026, week=w)
            finished_games_by_week[w] = w_games
            players_by_week[w] = w_players

        settled_count = 0
        updated_push_count = 0
        settled_game_names = set()
        
        for bet in candidate_bets:
            b_week = bet.week or 2
            w_games = finished_games_by_week.get(b_week, {})
            w_players = players_by_week.get(b_week, [])
            finished_game_ids = set(w_games.keys())
            finished_teams = set()
            for g in w_games.values():
                if g.get("home_team"):
                    finished_teams.add(clean_team_code(g["home_team"]))
                if g.get("away_team"):
                    finished_teams.add(clean_team_code(g["away_team"]))

            clean_b_team = clean_team_code(bet.team)
            
            # Se o jogo do time da aposta ainda não terminou, mantém o estado atual!
            is_game_finished = False
            if bet.game_id and bet.game_id in finished_game_ids:
                is_game_finished = True
            elif clean_b_team and clean_b_team in finished_teams:
                is_game_finished = True
                
            if not is_game_finished:
                # O jogo deste jogador ainda não terminou ou não iniciou
                continue
                
            # Verifica se temos as estatísticas oficiais carregadas para este time na semana correspondente
            team_has_stats = any(p.get("team") == clean_b_team for p in w_players)
            if not team_has_stats:
                # Jogo finalizado mas estatísticas ainda em processamento; preserva
                continue

            # Matching robusto estritamente dentro do time E DA SEMANA do jogador
            matched = match_player_in_stats(bet.player_name, clean_b_team, w_players, week=b_week)
            
            # Identificar nome amigável do jogo
            g_name = None
            if bet.game_id and bet.game_id in w_games:
                g_name = w_games[bet.game_id].get("name")
            if not g_name and clean_b_team:
                for fg in w_games.values():
                    if clean_b_team in (clean_team_code(fg.get("home_team")), clean_team_code(fg.get("away_team"))):
                        g_name = fg.get("name")
                        break
            if not g_name:
                g_name = f"Jogo do {clean_b_team}"

            prev_result = bet.result

            if matched is None:
                # Jogador inativo na partida terminada (não atuou / sem estatísticas na súmula oficial)
                # Pela regra oficial das casas de apostas (Betclic, FanDuel, etc.), apostas em jogadores inativos são anuladas (push / void)
                if prev_result != "push":
                    bet.result = "push"
                    bet.actual_value = 0.0
                    bet.profit_units = 0.0
                    bet.settled_at = datetime.now()
                    bet.is_locked = True
                    bet.notes = "Jogador inativo na partida (Aposta anulada / Push)"
                    settled_count += 1
                    settled_game_names.add(g_name)
                continue
                
            market_col = bet.market
            if market_col not in matched:
                continue
                
            val = matched.get(market_col, 0.0)
            actual_val = float(val) if val is not None else 0.0
            bet.actual_value = actual_val
            bet.settled_at = datetime.now()
            bet.is_locked = True
            bet.notes = f"Súmula oficial: {matched.get('player_display_name', bet.player_name)} ({clean_b_team}) = {actual_val} yds"
            
            if bet.side == "over":
                if actual_val > bet.line:
                    bet.result = "won"
                    bet.profit_units = round((bet.odds - 1.0) * bet.units, 2)
                elif actual_val < bet.line:
                    bet.result = "lost"
                    bet.profit_units = round(-1.0 * bet.units, 2)
                else:
                    bet.result = "push"
                    bet.profit_units = 0.0
            elif bet.side == "under":
                if actual_val < bet.line:
                    bet.result = "won"
                    bet.profit_units = round((bet.odds - 1.0) * bet.units, 2)
                elif actual_val > bet.line:
                    bet.result = "lost"
                    bet.profit_units = round(-1.0 * bet.units, 2)
                else:
                    bet.result = "push"
                    bet.profit_units = 0.0
                    
            if prev_result == "pending":
                settled_count += 1
                settled_game_names.add(g_name)
            elif prev_result == "push" and bet.result != "push":
                updated_push_count += 1
                settled_game_names.add(g_name)
            
        db.commit()
        games_str = f"{len(settled_game_names)} partidas finalizadas" if len(settled_game_names) > 2 else (", ".join(sorted(settled_game_names)) if settled_game_names else "jogos finalizados")
        
        remaining_query = db.query(Bet).filter(Bet.result == "pending")
        if portfolio_type:
            remaining_query = remaining_query.filter(Bet.portfolio_type == portfolio_type)
        remaining = remaining_query.count()

        msg_parts = []
        if settled_count > 0:
            msg_parts.append(f"{settled_count} apostas liquidadas")
        if updated_push_count > 0:
            msg_parts.append(f"{updated_push_count} apostas anteriormente pendentes/push atualizadas com súmula oficial")
        if not msg_parts:
            msg_parts.append("Nenhuma nova aposta para liquidar no momento")
            
        action_msg = " e ".join(msg_parts)
        return {
            "settled": settled_count + updated_push_count,
            "newly_settled": settled_count,
            "re_settled": updated_push_count,
            "remaining_pending": remaining,
            "message": f"{action_msg} de {games_str}! ({remaining} apostas aguardam os próximos jogos da rodada)"
        }
    finally:
        db.close()

@app.post("/api/portfolio/simulate-settlement")
def simulate_portfolio_settlement(portfolio_type: Optional[str] = None):
    """
    Modo de Teste / Demonstração:
    Liquida apostas pendentes usando as probabilidades do modelo APENAS para jogos futuros não iniciados.
    Partidas já jogadas ou em andamento NUNCA são simuladas nem sobrescritas.
    """
    db = SessionLocal()
    try:
        locked_game_ids, locked_teams = get_locked_games_and_teams(2026)
        query = db.query(Bet).filter(Bet.result == "pending", Bet.is_locked == False)
        if locked_teams:
            query = query.filter(~Bet.team.in_(locked_teams))
        if locked_game_ids:
            query = query.filter(~Bet.game_id.in_(locked_game_ids))
        if portfolio_type:
            query = query.filter(Bet.portfolio_type == portfolio_type)
        pending_bets = query.all()
        if not pending_bets:
            return {"settled": 0, "message": "Nenhuma aposta pendente de jogos futuros para simular."}
            
        np.random.seed(int(datetime.now().timestamp()) % 10000)
        settled_count = 0
        for bet in pending_bets:
            prob = bet.model_probability if bet.model_probability and 0 < bet.model_probability < 1 else (1.0 / bet.odds)
            win = np.random.rand() < prob
            
            if win:
                bet.result = "won"
                bet.profit_units = round((bet.odds - 1.0) * bet.units, 2)
                bet.actual_value = round(bet.line + np.random.uniform(5.0, 22.0) if bet.side == "over" else max(0.0, bet.line - np.random.uniform(4.0, 18.0)), 1)
            else:
                bet.result = "lost"
                bet.profit_units = round(-1.0 * bet.units, 2)
                bet.actual_value = round(max(0.0, bet.line - np.random.uniform(3.0, 15.0)) if bet.side == "over" else bet.line + np.random.uniform(4.0, 20.0), 1)
                
            bet.settled_at = datetime.now()
            settled_count += 1
            
        db.commit()
        return {
            "settled": settled_count,
            "message": f"{settled_count} apostas de jogos futuros liquidadas no modo de simulação."
        }
    finally:
        db.close()

@app.post("/api/portfolio/reset-settlement")
def reset_portfolio_settlement(portfolio_type: Optional[str] = None):
    db = SessionLocal()
    try:
        locked_game_ids, locked_teams = get_locked_games_and_teams(2026)
        query = db.query(Bet).filter(Bet.is_locked == False)
        if locked_teams:
            query = query.filter(~Bet.team.in_(locked_teams))
        if locked_game_ids:
            query = query.filter(~Bet.game_id.in_(locked_game_ids))
        if portfolio_type:
            query = query.filter(Bet.portfolio_type == portfolio_type)
        bets = query.all()
        reset_count = 0
        for b in bets:
            b.result = "pending"
            b.profit_units = 0.0
            b.actual_value = None
            b.settled_at = None
            reset_count += 1
        db.commit()
        return {
            "reset": reset_count,
            "message": f"{reset_count} apostas de simulação resetadas para pendente. Apostas de jogos oficiais finalizados foram preservadas intactas."
        }
    finally:
        db.close()

@app.post("/api/portfolio/{bet_id}/manual-settle")
def manual_settle_bet(bet_id: int, req: PortfolioManualSettleRequest):
    db = SessionLocal()
    try:
        b = db.query(Bet).filter(Bet.id == bet_id).first()
        if not b:
            raise HTTPException(status_code=404, detail="Aposta não encontrada.")
            
        locked_game_ids, locked_teams = get_locked_games_and_teams(b.season or 2026)
        if b.is_locked or (b.team and b.team in locked_teams) or (b.game_id and b.game_id in locked_game_ids):
            raise HTTPException(
                status_code=400,
                detail="Esta aposta pertence a um jogo já iniciado/concluído com súmula oficial e está bloqueada contra alterações manuais."
            )
            
        b.result = req.result
        if req.actual_value is not None:
            b.actual_value = req.actual_value
            
        if req.result == "won":
            b.profit_units = round((b.odds - 1.0) * b.units, 2)
        elif req.result == "lost":
            b.profit_units = round(-1.0 * b.units, 2)
        elif req.result == "push":
            b.profit_units = 0.0
        else:
            b.result = "pending"
            b.profit_units = 0.0
            
        b.settled_at = datetime.now() if req.result != "pending" else None
        db.commit()
        return {"status": "success", "bet_id": b.id, "result": b.result, "profit_units": b.profit_units}
    finally:
        db.close()

@app.delete("/api/portfolio/{bet_id}")
def delete_portfolio_bet(bet_id: int):
    db = SessionLocal()
    try:
        b = db.query(Bet).filter(Bet.id == bet_id).first()
        if not b:
            raise HTTPException(status_code=404, detail="Aposta não encontrada.")
            
        locked_game_ids, locked_teams = get_locked_games_and_teams(b.season or 2026)
        if b.is_locked or b.result in ('won', 'lost', 'push') or (b.team and b.team in locked_teams) or (b.game_id and b.game_id in locked_game_ids):
            raise HTTPException(
                status_code=400,
                detail="Esta aposta está bloqueada (jogo iniciado ou já liquidado) e não pode ser excluída do histórico."
            )
        db.delete(b)
        db.commit()
        return {"status": "deleted", "bet_id": bet_id}
    finally:
        db.close()

@app.delete("/api/portfolio/clear")
def clear_portfolio(portfolio_type: Optional[str] = None):
    db = SessionLocal()
    try:
        locked_game_ids, locked_teams = get_locked_games_and_teams(2026)
        query = db.query(Bet).filter(
            Bet.result == "pending",
            Bet.is_locked == False
        )
        if locked_teams:
            query = query.filter(~Bet.team.in_(locked_teams))
        if locked_game_ids:
            query = query.filter(~Bet.game_id.in_(locked_game_ids))
        if portfolio_type:
            query = query.filter(Bet.portfolio_type == portfolio_type)
        deleted = query.delete(synchronize_session=False)
        db.commit()
        return {
            "status": "cleared",
            "deleted": deleted,
            "message": f"{deleted} apostas pendentes desbloqueadas foram removidas. Apostas de jogos iniciados ou liquidados foram preservadas com segurança."
        }
    finally:
        db.close()


