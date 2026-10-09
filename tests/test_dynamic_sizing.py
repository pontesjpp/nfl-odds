from nfl_odds.betting.dynamic_sizing import calculate_smart_units, compute_portfolio_exposure_and_stats

def test_ev_filter_boundaries():
    res_low = calculate_smart_units(ev_percent=1.0)
    assert res_low["status"] == "EXCLUDED_BY_EV_FILTER"
    assert res_low["final_units"] == 0.0

    res_high = calculate_smart_units(ev_percent=45.0)
    assert res_high["status"] == "EXCLUDED_BY_EV_FILTER"
    assert res_high["final_units"] == 0.0

    res_valid = calculate_smart_units(ev_percent=7.5, market="receiving_yards")
    assert res_valid["status"] == "APPROVED"
    assert res_valid["final_units"] == 1.0

def test_market_weights():
    # Rushing: 1.20x
    res_rush = calculate_smart_units(ev_percent=6.0, market="rushing_yards", apply_high_ev_haircut=False)
    assert res_rush["market_weight"] == 1.20
    assert res_rush["final_units"] == 1.25

    # Passing: 0.80x (reativado sob calibrador dual-side)
    res_pass = calculate_smart_units(ev_percent=6.0, market="passing_yards", apply_high_ev_haircut=False)
    assert res_pass["market_weight"] == 0.80
    assert res_pass["status"] == "APPROVED"
    assert res_pass["final_units"] == 0.75

    # Receiving: 1.00x
    res_rec = calculate_smart_units(ev_percent=6.0, market="receiving_yards", apply_high_ev_haircut=False)
    assert res_rec["market_weight"] == 1.00
    assert res_rec["final_units"] == 1.00

def test_ai_veto():
    res_veto = calculate_smart_units(ev_percent=6.0, recommendation_adjustment="AVOID")
    assert res_veto["status"] == "VETOED_BY_AI"
    assert res_veto["final_units"] == 0.0

def test_over_vs_under_polarities():
    res_over_caution = calculate_smart_units(
        ev_percent=7.0, 
        side="over", 
        market="receiving_yards",
        ai_multiplier=0.65, 
        recommendation_adjustment="CAUTION"
    )
    assert res_over_caution["status"] == "APPROVED"
    assert res_over_caution["final_units"] <= 0.75

    res_under_boost = calculate_smart_units(
        ev_percent=7.0, 
        side="under", 
        market="receiving_yards",
        ai_multiplier=1.30, 
        recommendation_adjustment="BOOST"
    )
    assert res_under_boost["status"] == "APPROVED"
    assert res_under_boost["final_units"] == 1.25

def test_discretization_and_clamping():
    res_boost = calculate_smart_units(
        ev_percent=16.0, 
        max_ev=20.0,
        market="receiving_yards", 
        ai_multiplier=1.35, 
        recommendation_adjustment="BOOST", 
        apply_high_ev_haircut=False
    )
    assert res_boost["final_units"] == 1.75
    assert (res_boost["final_units"] * 4) % 1 == 0

def test_high_ev_haircut():
    # Bets with EV > 25.0% get 0.80x haircut factor
    res_high_ev = calculate_smart_units(ev_percent=28.0, market="receiving_yards", apply_high_ev_haircut=True)
    assert res_high_ev["high_ev_haircut"] == 0.80
    assert res_high_ev["final_units"] == 1.00

    # Bets with EV <= 25.0% do not get haircut
    res_med_ev = calculate_smart_units(ev_percent=12.0, market="receiving_yards", apply_high_ev_haircut=True)
    assert res_med_ev["high_ev_haircut"] == 1.00
    assert res_med_ev["final_units"] == 1.00

def test_tail_penalty():
    res_normal = calculate_smart_units(ev_percent=7.0, market="receiving_yards", z_distance=0.3)
    res_tail = calculate_smart_units(ev_percent=7.0, market="receiving_yards", z_distance=1.8)
    assert res_tail["tail_penalty"] == 0.75
    assert res_tail["final_units"] < res_normal["final_units"]

def test_portfolio_stats():
    bets = [
        {"player_name": "P1", "units": 0.5, "ev_percent": 3.0},
        {"player_name": "P2", "units": 1.0, "ev_percent": 6.0},
        {"player_name": "P3", "units": 1.75, "ev_percent": 12.0, "ai_sizing_rationale": "High Conviction"},
    ]
    stats = compute_portfolio_exposure_and_stats(bets)
    assert stats["total_units_staked"] == 3.25
    assert stats["avg_stake"] == 1.08
    assert stats["highest_conviction_pick"]["player_name"] == "P3"
    assert stats["highest_conviction_pick"]["units"] == 1.75

if __name__ == "__main__":
    test_ev_filter_boundaries()
    test_ai_veto()
    test_over_vs_under_polarities()
    test_discretization_and_clamping()
    test_tail_penalty()
    test_portfolio_stats()
    print("All dynamic sizing unit tests PASSED successfully!")
