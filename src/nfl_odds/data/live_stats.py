import re
import requests
import polars as pl
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

ESPN_TEAM_MAP = {
    'LAR': 'LA',
    'WSH': 'WAS'
}

def clean_team_code(code: Optional[str]) -> Optional[str]:
    if not code:
        return code
    return ESPN_TEAM_MAP.get(code.upper(), code.upper())

def normalize_name(name: Optional[str]) -> str:
    if not name:
        return ''
    # Remove generational suffixes (Jr., Sr., III, II, IV)
    cleaned = re.sub(r'\b(jr|sr|iii|ii|iv)\b\.?', '', name, flags=re.IGNORECASE)
    # Remove all non-alphanumeric characters
    return re.sub(r'[^a-zA-Z0-9]', '', cleaned).lower()

_scoreboard_cache: Dict[Tuple[int, int], Dict[str, Any]] = {}

def fetch_espn_scoreboard(season: int = 2026, week: int = 1, force: bool = False) -> List[Dict[str, Any]]:
    """
    Obtém a lista atualizada de todos os jogos da rodada diretamente da API pública da ESPN.
    Retorna placar, status ('finished', 'in_progress', 'scheduled') e event_id.
    """
    import time
    now_ts = time.time()
    cache_key = (season, week)
    cached = _scoreboard_cache.get(cache_key)
    if not force and cached and (now_ts - cached["ts"]) < 15.0:
        return cached["data"]

    url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={season}&seasontype=2&week={week}"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        sb = res.json()
    except Exception as e:
        print(f"Erro ao consultar ESPN scoreboard (semana {week}): {e}")
        return cached["data"] if cached else []

    games = []
    events = sb.get("events", [])
    for ev in events:
        try:
            competitions = ev.get("competitions", [])
            if not competitions:
                continue
            comp = competitions[0]
            status_obj = comp.get("status", {}).get("type", {})
            completed = bool(status_obj.get("completed", False))
            status_name = status_obj.get("name", "")
            status_desc = status_obj.get("description", "")
            
            competitors = comp.get("competitors", [])
            home_comp = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away_comp = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not home_comp or not away_comp:
                continue

            home_team = clean_team_code(home_comp.get("team", {}).get("abbreviation"))
            away_team = clean_team_code(away_comp.get("team", {}).get("abbreviation"))
            
            home_score = int(home_comp["score"]) if home_comp.get("score") is not None else None
            away_score = int(away_comp["score"]) if away_comp.get("score") is not None else None
            
            if completed or status_name == "STATUS_FINAL":
                status = "finished"
            elif status_name == "STATUS_IN_PROGRESS" or "In Progress" in status_desc:
                status = "in_progress"
            else:
                status = "scheduled"

            game_id = f"{season}_{week:02d}_{away_team}_{home_team}"

            games.append({
                "game_id": game_id,
                "event_id": str(ev.get("id")),
                "name": ev.get("name"),
                "home_team": home_team,
                "away_team": away_team,
                "home_score": home_score,
                "away_score": away_score,
                "status": status,
                "completed": completed or (status == "finished"),
                "status_detail": status_desc,
                "period": comp.get("status", {}).get("period"),
                "clock": comp.get("status", {}).get("displayClock")
            })
        except Exception as e:
            print(f"Erro ao processar jogo individual da ESPN: {e}")

    if games:
        _scoreboard_cache[cache_key] = {"ts": now_ts, "data": games}

    return games

_boxscore_cache: Dict[str, Dict[str, Any]] = {}

def fetch_espn_game_boxscore(event_id: str) -> Optional[Dict[str, Any]]:
    """
    Busca o Box Score detalhado de uma partida na ESPN por event_id.
    Retorna estatísticas individuais (passing, rushing, receiving) de todos os jogadores.
    """
    if event_id in _boxscore_cache:
        return _boxscore_cache[event_id]

    url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={event_id}"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"Erro ao consultar ESPN summary para event {event_id}: {e}")
        return None

    box = data.get("boxscore", {})
    team_players_data = box.get("players", [])

    all_athletes: List[Dict[str, Any]] = []

    for team_data in team_players_data:
        raw_team = team_data.get("team", {}).get("abbreviation")
        team_code = clean_team_code(raw_team)

        player_map: Dict[str, Dict[str, Any]] = {}

        for stat_group in team_data.get("statistics", []):
            cat_name = stat_group.get("name") # passing, rushing, receiving
            keys = stat_group.get("keys", [])
            for ath in stat_group.get("athletes", []):
                a_info = ath.get("athlete", {})
                aid = str(a_info.get("id", ""))
                if not aid:
                    continue

                if aid not in player_map:
                    display_name = a_info.get("displayName", "")
                    short_name = a_info.get("shortName")
                    if not short_name and display_name:
                        parts = display_name.split()
                        short_name = f"{parts[0][0]}.{parts[-1]}" if len(parts) >= 2 else display_name

                    headshot = a_info.get("headshot", {}).get("href")
                    position = a_info.get("position", {}).get("abbreviation")

                    player_map[aid] = {
                        "player_id": aid,
                        "player_name": short_name,
                        "player_display_name": display_name,
                        "headshot_url": headshot,
                        "position": position,
                        "team": team_code,
                        "passing_yards": 0.0,
                        "rushing_yards": 0.0,
                        "receiving_yards": 0.0,
                        "attempts": 0,
                        "completions": 0,
                        "carries": 0,
                        "receptions": 0,
                        "targets": 0,
                        "passing_tds": 0,
                        "rushing_tds": 0,
                        "receiving_tds": 0
                    }

                stats_vals = ath.get("stats", [])
                for k, v in zip(keys, stats_vals):
                    try:
                        if cat_name == "passing":
                            if k == "passingYards":
                                player_map[aid]["passing_yards"] = float(v)
                            elif k == "completions/passingAttempts":
                                comp, att = v.split("/")
                                player_map[aid]["completions"] = int(comp)
                                player_map[aid]["attempts"] = int(att)
                            elif k == "passingTouchdowns":
                                player_map[aid]["passing_tds"] = int(v)
                        elif cat_name == "rushing":
                            if k == "rushingYards":
                                player_map[aid]["rushing_yards"] = float(v)
                            elif k == "rushingAttempts":
                                player_map[aid]["carries"] = int(v)
                            elif k == "rushingTouchdowns":
                                player_map[aid]["rushing_tds"] = int(v)
                        elif cat_name == "receiving":
                            if k == "receivingYards":
                                player_map[aid]["receiving_yards"] = float(v)
                            elif k == "receptions":
                                player_map[aid]["receptions"] = int(v)
                            elif k == "receivingTargets":
                                player_map[aid]["targets"] = int(v)
                            elif k == "receivingTouchdowns":
                                player_map[aid]["receiving_tds"] = int(v)
                    except Exception:
                        pass

        all_athletes.extend(player_map.values())

    result = {
        "event_id": event_id,
        "athletes": all_athletes
    }
    _boxscore_cache[event_id] = result
    return result

def get_all_finished_game_stats(season: int = 2026, week: int = 1) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Obtém a lista de todas as partidas finalizadas e um catálogo completo de jogadores com estatísticas oficiais.
    Garante que times de partidas finalizadas tenham dados consolidados.
    Retorna: (finished_games_dict by game_id, all_player_stats_list)
    """
    scoreboard = fetch_espn_scoreboard(season=season, week=week, force=True)
    finished_games_dict: Dict[str, Dict[str, Any]] = {}
    all_players: List[Dict[str, Any]] = []

    # 1. Carregar estatísticas via ESPN para jogos finalizados
    for g in scoreboard:
        if g.get("completed"):
            gid = g["game_id"]
            finished_games_dict[gid] = g
            event_id = g.get("event_id")
            if event_id:
                bdata = fetch_espn_game_boxscore(event_id)
                if bdata and bdata.get("athletes"):
                    for a in bdata["athletes"]:
                        a_copy = dict(a)
                        a_copy["game_id"] = gid
                        a_copy["week"] = week
                        a_copy["season"] = season
                        all_players.append(a_copy)

    # 2. Carregar estatísticas via nflreadpy como complemento/fallback (ex: jogos anteriores)
    try:
        import nflreadpy as nfl
        import pandas as pd
        stats_nfl = nfl.load_player_stats([season])
        if isinstance(stats_nfl, pd.DataFrame):
            stats_nfl = pl.from_pandas(stats_nfl)
        week_stats = stats_nfl.filter(pl.col("week") == week)
        
        # Mapear times já preenchidos pela ESPN para não duplicar
        existing_teams = set(p["team"] for p in all_players)
        
        for row in week_stats.iter_rows(named=True):
            r_team = clean_team_code(row.get("team"))
            if r_team in existing_teams:
                continue
                
            gid = row.get("game_id")
            if gid:
                finished_games_dict[gid] = {
                    "game_id": gid,
                    "home_team": row.get("opponent_team") if r_team != row.get("team") else r_team,
                    "away_team": r_team,
                    "status": "finished",
                    "completed": True
                }
                
            all_players.append({
                "player_id": str(row.get("player_id", "")),
                "player_name": row.get("player_name"),
                "player_display_name": row.get("player_display_name"),
                "headshot_url": row.get("headshot_url"),
                "position": row.get("position"),
                "team": r_team,
                "game_id": gid,
                "week": week,
                "season": season,
                "passing_yards": float(row.get("passing_yards") or 0.0),
                "passing_tds": int(row.get("passing_tds") or 0),
                "attempts": int(row.get("attempts") or 0),
                "completions": int(row.get("completions") or 0),
                "rushing_yards": float(row.get("rushing_yards") or 0.0),
                "rushing_tds": int(row.get("rushing_tds") or 0),
                "carries": int(row.get("carries") or 0),
                "receiving_yards": float(row.get("receiving_yards") or 0.0),
                "receiving_tds": int(row.get("receiving_tds") or 0),
                "receptions": int(row.get("receptions") or 0),
                "targets": int(row.get("targets") or 0),
            })
    except Exception as e:
        print(f"Erro ao complementar estatísticas com nflreadpy: {e}")

    return finished_games_dict, all_players

def match_player_in_stats(
    bet_player_name: str, 
    bet_team: str, 
    players_list: List[Dict[str, Any]], 
    week: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Realiza matching robusto de jogador GARANTINDO isolamento total de time (Team Scoping)
    e isolamento rigoroso por rodada (Week Scoping).
    NUNCA aceita match de um jogador de outro time ou de outra semana.
    """
    if not bet_team or not players_list:
        return None

    clean_bet_team = clean_team_code(bet_team)
    team_players = [
        p for p in players_list 
        if p.get("team") == clean_bet_team and (week is None or p.get("week") is None or p.get("week") == week)
    ]
    if not team_players:
        return None

    p_norm = normalize_name(bet_player_name)

    # 1. Match direto ou normalizado de nome completo ou display_name
    for p in team_players:
        dn_norm = normalize_name(p.get("player_display_name"))
        sn_norm = normalize_name(p.get("player_name"))
        if p_norm and (p_norm == dn_norm or p_norm == sn_norm):
            return p

    # 2. Match por Primeira Inicial + Sobrenome (ex: J.Cook -> James Cook III, H.Fannin -> Harold Fannin Jr.)
    parts = bet_player_name.replace(".", " ").split()
    if len(parts) >= 2:
        init = parts[0][0].lower()
        last_norm = normalize_name(parts[-1])
        for p in team_players:
            d_parts = (p.get("player_display_name") or "").replace(".", " ").split()
            if len(d_parts) >= 2:
                d_init = d_parts[0][0].lower()
                clean_d_last = [x for x in d_parts[1:] if x.lower() not in ("jr", "sr", "iii", "ii", "iv", "jr.", "sr.")]
                d_last = normalize_name(clean_d_last[-1]) if clean_d_last else normalize_name(d_parts[-1])
                if init == d_init and last_norm == d_last:
                    return p

    # 3. Match por sobrenome único no time
    if len(parts) >= 2:
        last_norm = normalize_name(parts[-1])
        cands = []
        for p in team_players:
            d_parts = (p.get("player_display_name") or "").replace(".", " ").split()
            clean_d_last = [x for x in d_parts if x.lower() not in ("jr", "sr", "iii", "ii", "iv", "jr.", "sr.")]
            if clean_d_last and normalize_name(clean_d_last[-1]) == last_norm:
                cands.append(p)
        if len(cands) == 1:
            return cands[0]

    return None
