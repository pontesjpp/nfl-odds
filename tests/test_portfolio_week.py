import pytest
from fastapi.testclient import TestClient
from nfl_odds.dashboard.api import app

def test_portfolio_week_filter():
    client = TestClient(app)
    
    # Test all weeks
    res_all = client.get("/api/portfolio?portfolio_type=safe&week=all")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert "available_weeks" in data_all
    assert "summary" in data_all
    assert data_all["selected_week"] == "all"
    
    # Test specific week 1
    res_w1 = client.get("/api/portfolio?portfolio_type=safe&week=1")
    assert res_w1.status_code == 200
    data_w1 = res_w1.json()
    assert data_w1["selected_week"] == "1"
    for bet in data_w1["bets"]:
        if bet.get("week") is not None:
            assert bet["week"] == 1
