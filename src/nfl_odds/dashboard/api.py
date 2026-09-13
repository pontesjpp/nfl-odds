from typing import List, Optional
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from pydantic import BaseModel
import polars as pl
import pandas as pd
import numpy as np
import os
import math

from nfl_odds.models.train import PlayerPropModel
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
)

class LoginRequest(BaseModel):
    password: str
    totp_code: Optional[str] = None

class SystemModeRequest(BaseModel):
    read_only: bool
    admin_secret: Optional[str] = None

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

# Load resources
models = {}
for m in ["rushing_yards", "receiving_yards", "passing_yards"]:
    try:
        path = f"data/{m}_model.joblib"
        if os.path.exists(path):
            models[m] = PlayerPropModel.load(path)
    except Exception as e:
        print(f"Error loading {m} model: {e}")

df_live = pl.DataFrame()
try:
    if os.path.exists("data/live_features.parquet"):
        df_live = pl.read_parquet("data/live_features.parquet")
except Exception:
    pass

df_backtest = pd.DataFrame()
try:
    if os.path.exists("data/backtest_results.parquet"):
        df_backtest = pl.read_parquet("data/backtest_results.parquet").to_pandas()
        df_backtest = df_backtest.replace([np.inf, -np.inf], None)
        df_backtest = df_backtest.where(pd.notnull(df_backtest), None)
except Exception:
    pass

df_live_bets = pd.DataFrame()
try:
    if os.path.exists("data/live_value_bets.parquet"):
        df_live_bets = pl.read_parquet("data/live_value_bets.parquet").to_pandas()
        df_live_bets = df_live_bets.replace([np.inf, -np.inf], None)
        df_live_bets = df_live_bets.where(pd.notnull(df_live_bets), None)
except Exception:
    pass

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
    return {
        "models_loaded": list(models.keys()),
        "live_data_loaded": not df_live.is_empty(),
        "live_bets_loaded": not df_live_bets.empty,
        "read_only": READ_ONLY_MODE
    }

@app.get("/api/players")
def get_players(market: str = None):
    if df_live.is_empty():
        return []
    latest_week = df_live["week"].max()
    df_latest = df_live.filter(pl.col("week") >= latest_week - 4)
    
    if market == "passing_yards":
        df_latest = df_latest.filter(pl.col("position") == "QB")
    elif market == "rushing_yards":
        df_latest = df_latest.filter(pl.col("position").is_in(["RB", "QB", "WR", "FB"]))
    elif market == "receiving_yards":
        df_latest = df_latest.filter(pl.col("position").is_in(["WR", "TE", "RB"]))
        
    cols = ["player_name", "position", "team"]
    if "player_display_name" in df_latest.columns:
        cols.append("player_display_name")
    if "opponent_team" in df_latest.columns:
        cols.append("opponent_team")
        
    players_df = df_latest.select(cols).unique()
    if "player_display_name" in players_df.columns:
        players_df = players_df.sort("player_display_name")
    else:
        players_df = players_df.sort("player_name")
        
    return players_df.to_pandas().replace([np.inf, -np.inf], None).where(pd.notnull(players_df.to_pandas()), None).to_dict(orient="records")

@app.get("/api/players/{player_name}/features")
def get_player_features(
    player_name: str, 
    market: str = None, 
    espn_id: str = None, 
    opponent: str = None,
    side: str = None,
    season: int = 2026,
    week: int = 1
):
    global df_live
    try:
        if os.path.exists("data/live_features.parquet"):
            df_live = pl.read_parquet("data/live_features.parquet")
    except Exception:
        pass
        
    if df_live.is_empty():
        raise HTTPException(status_code=400, detail="Data not loaded")
    
    player_data_all = pl.DataFrame()
    if espn_id and espn_id != "undefined" and espn_id != "null":
        # Cast espn_id column to str in case it's integer in parquet
        player_data_all = df_live.filter(pl.col("espn_id").cast(pl.Utf8) == str(espn_id))
        
    if player_data_all.is_empty():
        clean_name = player_name.strip()
        player_data_all = df_live.filter(
            (pl.col("player_name") == clean_name) |
            (pl.col("player_display_name") == clean_name) |
            (pl.col("player_name").str.to_lowercase() == clean_name.lower()) |
            (pl.col("player_display_name").str.to_lowercase() == clean_name.lower())
        )
        
    if player_data_all.is_empty():
        raise HTTPException(status_code=404, detail="Player not found")
        
    latest_week = player_data_all["week"].max()
    player_data = player_data_all.filter(pl.col("week") == latest_week)
    
    # Position fallback if multiple players share the name
    if len(player_data) > 1 and market:
        if market == "passing_yards":
            player_data = player_data.filter(pl.col("position") == "QB")
        elif market == "rushing_yards":
            player_data = player_data.filter(pl.col("position").is_in(["RB", "QB", "WR"]))
        elif market == "receiving_yards":
            player_data = player_data.filter(pl.col("position").is_in(["WR", "TE", "RB"]))
        if player_data.is_empty():
            player_data = player_data_all.filter(pl.col("week") == latest_week)
        
    features_to_return = []
    importances = {}
    
    if market:
        if market not in models:
            try:
                path = f"data/{market}_model.joblib"
                if os.path.exists(path):
                    models[market] = PlayerPropModel.load(path)
            except Exception as e:
                print(f"Could not dynamic load {market} model: {e}")
                
        if market in models:
            m = models[market]
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
            opp_rows = df_live.filter((pl.col("opponent_team") == opp_code) | (pl.col("team") == opp_code))
            if not opp_rows.is_empty():
                latest_opp_week = opp_rows["week"].max()
                opp_def_data = opp_rows.filter(pl.col("week") == latest_opp_week).head(1)
                def_features = [c for c in features_to_return if c.startswith("def_") or "opp" in c]
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
            opp_profile = get_team_defense_profile(
                active_opponent, 
                season=season, 
                week=week, 
                market=market, 
                side=side
            )
        except Exception as e:
            print(f"Error computing defense profile for {active_opponent}: {e}")
            
    stats_dict = {}
    for f in features_to_return:
        if f in player_data.columns:
            val = player_data[f][0]
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
def get_league_defense_rankings(season: int = 2026, week: int = 1):
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
        if df_live.is_empty():
            raise HTTPException(status_code=400, detail="Data not loaded")
        
        if req.market not in models:
            try:
                path = f"data/{req.market}_model.joblib"
                if os.path.exists(path):
                    models[req.market] = PlayerPropModel.load(path)
            except Exception:
                pass
                
        if req.market not in models:
            raise HTTPException(status_code=400, detail=f"Model for {req.market} not loaded")
            
        model_to_use = models[req.market]
            
        clean_name = req.player_name.strip()
        player_data_all = df_live.filter(
            (pl.col("player_name") == clean_name) |
            (pl.col("player_display_name") == clean_name) |
            (pl.col("player_name").str.to_lowercase() == clean_name.lower()) |
            (pl.col("player_display_name").str.to_lowercase() == clean_name.lower())
        )
        if player_data_all.is_empty():
            raise HTTPException(status_code=404, detail=f"Player '{req.player_name}' not found")
            
        latest_week = player_data_all["week"].max()
        player_data = player_data_all.filter(pl.col("week") == latest_week)
        
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
                opp_rows = df_live.filter((pl.col("opponent_team") == opp_code) | (pl.col("team") == opp_code))
                if not opp_rows.is_empty():
                    latest_opp_week = opp_rows["week"].max()
                    opp_def_data = opp_rows.filter(pl.col("week") == latest_opp_week).head(1)
                    def_features = [c for c in model_to_use.features if c.startswith("def_") or "opp" in c]
                    for c in def_features:
                        if c in opp_def_data.columns and c in player_data.columns:
                            val = opp_def_data[c][0]
                            if val is not None:
                                player_data = player_data.with_columns(pl.lit(val).alias(c))
                    active_opponent = opp_code
            
        lines_arr = np.array([req.line])
        prob_over = float(model_to_use.probability_over_line(player_data, lines_arr)[0])
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
    
    fair_odds_over = 1.0 / prob_over if prob_over > 0.0001 else 0.0
    fair_odds_under = 1.0 / prob_under if prob_under > 0.0001 else 0.0
    
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

schedule_cache = None

@app.get("/api/schedule")
def get_schedule(refresh: bool = False):
    global schedule_cache
    if schedule_cache is not None and not refresh:
        return schedule_cache
        
    try:
        import nflreadpy as nfl
        df = nfl.load_schedules([2026])
        if isinstance(df, pd.DataFrame):
            df = pl.from_pandas(df)
        week1 = df.filter(pl.col('week') == 1)
        
        cols = ['game_id', 'home_team', 'away_team', 'stadium', 'location', 'gameday', 'gametime', 'home_score', 'away_score']
        avail_cols = [c for c in cols if c in week1.columns]
        week1 = week1.select(avail_cols)
        records = week1.to_dicts()

        # Enriquecer com ESPN live scoreboard (placar em tempo real, status de finalizado / em andamento)
        try:
            from nfl_odds.data.live_stats import fetch_espn_scoreboard, clean_team_code
            espn_games = fetch_espn_scoreboard(2026, 1, force=refresh)
            espn_map = {}
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
                    else:
                        r['home_score'] = None
                        r['away_score'] = None
                        r['status'] = 'scheduled'
        except Exception as e:
            print(f"Erro ao enriquecer schedule com ESPN: {e}")
            for r in records:
                if r.get('home_score') is not None and r.get('away_score') is not None:
                    r['status'] = 'finished'
                else:
                    r['home_score'] = None
                    r['away_score'] = None
                    r['status'] = 'scheduled'

        schedule_cache = records
        return schedule_cache
    except Exception as e:
        print(f"Error loading schedule: {e}")
        return []

@app.get("/api/games/{game_id}/boxscore")
def get_game_boxscore(game_id: str):
    import nflreadpy as nfl
    from nfl_odds.data.live_stats import fetch_espn_scoreboard, fetch_espn_game_boxscore, clean_team_code
    try:
        sched = nfl.load_schedules([2026])
        if isinstance(sched, pd.DataFrame):
            sched = pl.from_pandas(sched)
        game_matches = sched.filter(pl.col("game_id") == game_id)
        if len(game_matches) == 0:
            raise HTTPException(status_code=404, detail="Jogo não encontrado.")
            
        game_info = game_matches.to_dicts()[0]
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
def get_live_bets(response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    # Always try to reload to get fresh data if it was generated in background
    global df_live_bets
    try:
        if os.path.exists("data/live_value_bets.parquet"):
            df_live_bets = pl.read_parquet("data/live_value_bets.parquet").to_pandas()
            if "ev_percent" in df_live_bets.columns:
                df_live_bets = df_live_bets.sort_values(by="ev_percent", ascending=False)
            df_live_bets = df_live_bets.replace([np.inf, -np.inf], None)
            df_live_bets = df_live_bets.where(pd.notnull(df_live_bets), None)
    except Exception:
        pass
        
    if df_live_bets.empty:
        return []
    return df_live_bets.to_dict(orient="records")

@app.get("/api/top-picks")
def get_top_picks(limit: int = 10, response: Response = None):
    if response:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    global df_live_bets
    try:
        if os.path.exists("data/live_value_bets.parquet"):
            df_live_bets = pl.read_parquet("data/live_value_bets.parquet").to_pandas()
            df_live_bets = df_live_bets.replace([np.inf, -np.inf], None)
            df_live_bets = df_live_bets.where(pd.notnull(df_live_bets), None)
    except Exception:
        pass
        
    if df_live_bets.empty:
        return []
        
    # Assegura que tem as colunas ev para ordenar
    sort_col = "ev_percent" if "ev_percent" in df_live_bets.columns else "ev_10_eur"
    
    # Filtra apenas picks com EV > 0, ordena e pega o top N
    top_picks = df_live_bets[df_live_bets[sort_col] > 0].sort_values(by=sort_col, ascending=False).head(limit)
    
    return top_picks.to_dict(orient="records")

import subprocess
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

_locked_cache = {"season": None, "ts": 0.0, "locked_game_ids": set(), "locked_teams": set()}

def get_locked_games_and_teams(season: int = 2026):
    """
    Identifica jogos cujos horários de início (kickoff) já passaram ou cujos placares oficiais já foram lançados.
    Qualquer aposta pertencente a esses times/jogos fica 100% bloqueada contra alterações/exclusões/reimportações.
    """
    import time
    now_ts = time.time()
    if _locked_cache["season"] == season and (now_ts - _locked_cache["ts"]) < 30.0:
        return _locked_cache["locked_game_ids"], _locked_cache["locked_teams"]
        
    locked_game_ids = set()
    locked_teams = set()
    now = datetime.now()

    # 1. ESPN Scoreboard (Tempo Real)
    try:
        from nfl_odds.data.live_stats import fetch_espn_scoreboard, clean_team_code
        espn_sb = fetch_espn_scoreboard(season=season, week=1)
        for eg in espn_sb:
            if eg.get("status") in ("finished", "in_progress") or eg.get("completed"):
                if eg.get("game_id"):
                    locked_game_ids.add(eg["game_id"])
                if eg.get("home_team"):
                    locked_teams.add(clean_team_code(eg["home_team"]))
                if eg.get("away_team"):
                    locked_teams.add(clean_team_code(eg["away_team"]))
    except Exception as e:
        print(f"Erro ao verificar partidas bloqueadas via ESPN: {e}")

    # 2. nflreadpy schedule (Fallback)
    try:
        import nflreadpy as nfl
        sched = nfl.load_schedules([season])
        if isinstance(sched, pd.DataFrame):
            sched = pl.from_pandas(sched)
            
        for row in sched.iter_rows(named=True):
            gid = row.get("game_id")
            h_team = clean_team_code(row.get("home_team"))
            a_team = clean_team_code(row.get("away_team"))
            h_score = row.get("home_score")
            a_score = row.get("away_score")
            gameday = row.get("gameday")
            gametime = row.get("gametime")
            
            is_locked = False
            # 1. Jogo concluído com placar oficial
            if h_score is not None and a_score is not None:
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
                    locked_teams.add(str(h_team))
                if a_team:
                    locked_teams.add(str(a_team))
    except Exception as e:
        print(f"Erro ao verificar partidas bloqueadas via nflreadpy: {e}")
        locked_game_ids.add("2026_01_NE_SEA")
        locked_teams.update(["NE", "SEA"])
        
    _locked_cache["season"] = season
    _locked_cache["ts"] = now_ts
    _locked_cache["locked_game_ids"] = locked_game_ids
    _locked_cache["locked_teams"] = locked_teams
    return locked_game_ids, locked_teams

@app.post("/api/run-pipeline")
def run_pipeline_api(request: Request):
    if not is_request_admin(request):
        raise HTTPException(
            status_code=403,
            detail="🔒 Apenas o Administrador autenticado com MFA pode atualizar odds e acionar a IA."
        )
    try:
        # Run the scraper
        subprocess.run(["python3", "src/nfl_odds/odds/betclic_scraper.py"], check=True)
        # Run the pipeline
        subprocess.run(["python3", "pipeline.py", "--live"], check=True)
        
        # Auto-sync portfolios for pending bets so recommendations and portfolio stay 100% aligned
        try:
            import_safe_picks(replace_pending=True)
            import_high_risk_picks(replace_pending=True)
            import_all_props(replace_pending=True)
        except Exception as sync_err:
            print(f"Auto-sync warning: {sync_err}")
            
        return {"status": "success"}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")

@app.get("/api/portfolio")
def get_portfolio(portfolio_type: str = "safe", response: Response = None):
    if response:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    db = SessionLocal()
    try:
        global df_live_bets
        live_safe_count = 0
        live_high_risk_count = 0
        live_all_props_count = 0
        if not df_live_bets.empty:
            ev_col = "ev_percent" if "ev_percent" in df_live_bets.columns else "ev_10_eur"
            live_safe_count = int(((df_live_bets[ev_col] >= 2.5) & (df_live_bets[ev_col] <= 15.0)).sum())
            live_high_risk_count = int((df_live_bets[ev_col] > 20.0).sum())
            # All props com EV positivo estrito
            df_positive = df_live_bets[df_live_bets[ev_col] > 0.0]
            live_all_props_count = len(df_positive.drop_duplicates(subset=["player_name", "market", "line"]))

        all_bets = db.query(Bet).all()
        safe_count = sum(1 for b in all_bets if (b.portfolio_type or "safe") == "safe")
        high_risk_count = sum(1 for b in all_bets if b.portfolio_type == "high_risk")
        all_props_count = sum(1 for b in all_bets if b.portfolio_type == "all_props")
        
        bets = [b for b in all_bets if (b.portfolio_type or "safe") == portfolio_type]
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
            
        locked_game_ids, locked_teams = get_locked_games_and_teams(2026)

        bets_data = []
        for b in reversed(bets):
            is_locked = bool(
                b.is_locked
                or b.result in ('won', 'lost', 'push')
                or (b.game_id and b.game_id in locked_game_ids)
                or (b.team and b.team in locked_teams)
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
            "high_risk_count": high_risk_count,
            "all_props_count": all_props_count,
            "live_safe_count": live_safe_count,
            "live_high_risk_count": live_high_risk_count,
            "live_all_props_count": live_all_props_count,
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
def import_safe_picks(replace_pending: bool = False):
    global df_live_bets
    try:
        if os.path.exists("data/live_value_bets.parquet"):
            df_live_bets = pl.read_parquet("data/live_value_bets.parquet").to_pandas()
            df_live_bets = df_live_bets.replace([np.inf, -np.inf], None)
            df_live_bets = df_live_bets.where(pd.notnull(df_live_bets), None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar odds: {e}")
        
    if df_live_bets.empty:
        return {"imported": 0, "message": "Nenhuma aposta ao vivo encontrada."}
        
    ev_col = "ev_percent" if "ev_percent" in df_live_bets.columns else "ev_10_eur"
    mask = (df_live_bets[ev_col] >= 2.5) & (df_live_bets[ev_col] <= 15.0)
    
    safe_df = df_live_bets[mask]
    
    locked_game_ids, locked_teams = get_locked_games_and_teams(2026)
    
    db = SessionLocal()
    imported_count = 0
    updated_count = 0
    skipped_locked_count = 0
    try:
        if replace_pending:
            del_query = db.query(Bet).filter(
                Bet.result == "pending",
                Bet.portfolio_type == "safe",
                Bet.is_locked == False
            )
            if locked_teams:
                del_query = del_query.filter(~Bet.team.in_(locked_teams))
            if locked_game_ids:
                del_query = del_query.filter(~Bet.game_id.in_(locked_game_ids))
            del_query.delete(synchronize_session=False)
            db.commit()

        for _, row in safe_df.iterrows():
            team = str(row.get("team", "")) if row.get("team") else None
            game_id = str(row.get("game_id", "")) if row.get("game_id") else None
            
            # SANITY CHECK: Nunca importar ou substituir apostas de partidas iniciadas/encerradas
            if (team and team in locked_teams) or (game_id and game_id in locked_game_ids):
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
                Bet.portfolio_type == "safe"
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
                    portfolio_type="safe",
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
            "replaced": replace_pending
        }
    finally:
        db.close()

@app.post("/api/portfolio/import-high-risk-picks")
def import_high_risk_picks(replace_pending: bool = False):
    global df_live_bets
    try:
        if os.path.exists("data/live_value_bets.parquet"):
            df_live_bets = pl.read_parquet("data/live_value_bets.parquet").to_pandas()
            df_live_bets = df_live_bets.replace([np.inf, -np.inf], None)
            df_live_bets = df_live_bets.where(pd.notnull(df_live_bets), None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar odds: {e}")
        
    if df_live_bets.empty:
        return {"imported": 0, "message": "Nenhuma aposta ao vivo encontrada."}
        
    ev_col = "ev_percent" if "ev_percent" in df_live_bets.columns else "ev_10_eur"
    # Regra estrita de alto risco: apenas EV > 20.0%
    mask = df_live_bets[ev_col] > 20.0
    
    hr_df = df_live_bets[mask]
    
    locked_game_ids, locked_teams = get_locked_games_and_teams(2026)
    
    db = SessionLocal()
    imported_count = 0
    updated_count = 0
    skipped_locked_count = 0
    try:
        if replace_pending:
            del_query = db.query(Bet).filter(
                Bet.result == "pending",
                Bet.portfolio_type == "high_risk",
                Bet.is_locked == False
            )
            if locked_teams:
                del_query = del_query.filter(~Bet.team.in_(locked_teams))
            if locked_game_ids:
                del_query = del_query.filter(~Bet.game_id.in_(locked_game_ids))
            del_query.delete(synchronize_session=False)
            db.commit()

        for _, row in hr_df.iterrows():
            team = str(row.get("team", "")) if row.get("team") else None
            game_id = str(row.get("game_id", "")) if row.get("game_id") else None
            
            # SANITY CHECK: Nunca importar ou substituir apostas de partidas iniciadas/encerradas
            if (team and team in locked_teams) or (game_id and game_id in locked_game_ids):
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
    global df_live_bets
    try:
        if os.path.exists("data/live_value_bets.parquet"):
            df_live_bets = pl.read_parquet("data/live_value_bets.parquet").to_pandas()
            df_live_bets = df_live_bets.replace([np.inf, -np.inf], None)
            df_live_bets = df_live_bets.where(pd.notnull(df_live_bets), None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar odds: {e}")
        
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
        
    locked_game_ids, locked_teams = get_locked_games_and_teams(2026)

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
                Bet.is_locked == False
            )
            if locked_teams:
                del_query = del_query.filter(~Bet.team.in_(locked_teams))
            if locked_game_ids:
                del_query = del_query.filter(~Bet.game_id.in_(locked_game_ids))
            del_query.delete(synchronize_session=False)
            db.commit()

        for _, row in target_df.iterrows():
            team = str(row.get("team", "")) if row.get("team") else None
            game_id = str(row.get("game_id", "")) if row.get("game_id") else None
            
            # SANITY CHECK: Não importar novas apostas para partidas já iniciadas ou encerradas
            if (team and team in locked_teams) or (game_id and game_id in locked_game_ids):
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
def settle_portfolio(portfolio_type: Optional[str] = None, game_id: Optional[str] = None):
    db = SessionLocal()
    try:
        query = db.query(Bet).filter(Bet.result == "pending")
        if portfolio_type:
            query = query.filter(Bet.portfolio_type == portfolio_type)
        if game_id:
            query = query.filter(Bet.game_id == game_id)
        pending_bets = query.all()
        if not pending_bets:
            return {"settled": 0, "message": "Nenhuma aposta pendente na carteira."}

        from nfl_odds.data.live_stats import (
            get_all_finished_game_stats,
            match_player_in_stats,
            clean_team_code
        )

        # 1. Carregar catálogo completo de jogos finalizados e estatísticas oficiais (ESPN + nflreadpy)
        finished_games_dict, all_players = get_all_finished_game_stats(season=2026, week=1)
        finished_game_ids = set(finished_games_dict.keys())
        finished_teams = set()
        for g in finished_games_dict.values():
            if g.get("home_team"):
                finished_teams.add(clean_team_code(g["home_team"]))
            if g.get("away_team"):
                finished_teams.add(clean_team_code(g["away_team"]))

        settled_count = 0
        settled_game_names = set()
        
        for bet in pending_bets:
            clean_b_team = clean_team_code(bet.team)
            
            # Se o jogo do time da aposta ainda não terminou, mantém pendente!
            is_game_finished = False
            if bet.game_id and bet.game_id in finished_game_ids:
                is_game_finished = True
            elif clean_b_team and clean_b_team in finished_teams:
                is_game_finished = True
                
            if not is_game_finished:
                # O jogo deste jogador ainda não terminou ou não iniciou
                continue
                
            # Verifica se temos as estatísticas oficiais carregadas para este time
            team_has_stats = any(p.get("team") == clean_b_team for p in all_players)
            if not team_has_stats:
                # Jogo finalizado mas estatísticas ainda em processamento; preserva pendente
                continue

            # Matching robusto estritamente dentro do time do jogador (Sem falso-match com outros times!)
            matched = match_player_in_stats(bet.player_name, clean_b_team, all_players)
            
            # Identificar nome amigável do jogo
            g_name = None
            if bet.game_id and bet.game_id in finished_games_dict:
                g_name = finished_games_dict[bet.game_id].get("name")
            if not g_name and clean_b_team:
                for fg in finished_games_dict.values():
                    if clean_b_team in (clean_team_code(fg.get("home_team")), clean_team_code(fg.get("away_team"))):
                        g_name = fg.get("name")
                        break
            if not g_name:
                g_name = f"Jogo do {clean_b_team}"

            if matched is None:
                # Jogador inativo na partida terminada (não atuou / sem estatísticas na súmula oficial)
                # Pela regra oficial das casas de apostas (Betclic, FanDuel, etc.), apostas em jogadores inativos são anuladas (push / void)
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
                    
            settled_count += 1
            settled_game_names.add(g_name)
            
        db.commit()
        games_str = f"{len(settled_game_names)} partidas finalizadas" if len(settled_game_names) > 2 else (", ".join(sorted(settled_game_names)) if settled_game_names else "jogos finalizados")
        remaining = len(pending_bets) - settled_count
        return {
            "settled": settled_count,
            "remaining_pending": remaining,
            "message": f"{settled_count} apostas de {games_str} liquidadas com estatísticas oficiais! ({remaining} apostas aguardam os próximos jogos da rodada)"
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


