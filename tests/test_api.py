import pytest
from fastapi.testclient import TestClient
from nfl_odds.dashboard.api import app

@pytest.fixture
def client():
    return TestClient(app)

def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "nfl-odds-api"

def test_status(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "models_loaded" in data
    assert "live_data_loaded" in data
    assert "live_bets_loaded" in data
    assert "read_only" in data

def test_get_teams(client):
    response = client.get("/api/teams")
    assert response.status_code == 200
    teams = response.json()
    assert len(teams) == 32
    assert any(t["code"] == "KC" for t in teams)

def test_get_players(client):
    response = client.get("/api/players")
    assert response.status_code == 200
    players = response.json()
    assert isinstance(players, list)
    assert len(players) > 0

def test_get_players_by_market(client):
    response = client.get("/api/players?market=passing_yards")
    assert response.status_code == 200
    players = response.json()
    assert isinstance(players, list)
    for p in players:
        assert p["position"] == "QB"

def test_get_player_features(client):
    response = client.get("/api/players/P.Mahomes/features?market=passing_yards")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)

def test_get_player_features_jared_goff_season_stats(client):
    """
    Regression test: Jared Goff played Game 1 in 2026 with 206 yds, 39 att, 26 cmp.
    Ensures that current season (2026) features are returned instead of 2025 week 18 (264.56 yds).
    """
    response = client.get("/api/players/Jared Goff/features?market=passing_yards")
    assert response.status_code == 200
    data = response.json()
    assert "passing_yards_season_avg" in data
    assert data["passing_yards_season_avg"]["value"] == 206.0
    assert data["attempts_season_avg"]["value"] == 39.0
    assert data["completions_season_avg"]["value"] == 26.0

def test_predict_prop(client):
    payload = {
        "player_name": "Patrick Mahomes",
        "market": "passing_yards",
        "line": 260.5,
        "odds_over": 1.90,
        "odds_under": 1.90,
        "stake": 100.0
    }
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "over" in data
    assert "under" in data
    assert "model_prob" in data["over"]
    assert "ev" in data["over"]

def test_live_bets(client):
    response = client.get("/api/live-bets")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_bets_alias(client):
    response = client.get("/api/bets")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_top_picks(client):
    response = client.get("/api/top-picks?limit=5")
    assert response.status_code == 200
    picks = response.json()
    assert isinstance(picks, list)
    assert len(picks) <= 5

def test_schedule(client):
    response = client.get("/api/schedule")
    assert response.status_code == 200
    sched = response.json()
    assert isinstance(sched, list)
    assert len(sched) > 0

def test_defense_rankings(client):
    response = client.get("/api/defense-rankings")
    assert response.status_code == 200
    data = response.json()
    assert "teams" in data
    assert data["total_teams"] == 32

def test_trim_memory_execution():
    from nfl_odds.dashboard.api import trim_memory
    # Should execute safely and silently without exception
    trim_memory()

def test_render_run_pipeline_safeguard(client, monkeypatch):
    import os
    from nfl_odds.dashboard.auth import create_admin_token
    token = create_admin_token()
    headers = {"Authorization": f"Bearer {token}"}

    monkeypatch.setenv("RENDER", "true")
    res = client.post("/api/run-pipeline", headers=headers)
    assert res.status_code == 400
    assert "512MB" in res.json()["detail"]

