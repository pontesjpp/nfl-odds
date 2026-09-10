from nfl_odds.betting.dynamic_sizing import calculate_smart_units, compute_portfolio_exposure_and_stats

def test_ev_filter_boundaries():
    res_low = calculate_smart_units(ev_percent=2.1)
    assert res_low["status"] == "EXCLUDED_BY_EV_FILTER"
    assert res_low["final_units"] == 0.0

    res_high = calculate_smart_units(ev_percent=18.5)
    assert res_high["status"] == "EXCLUDED_BY_EV_FILTER"
    assert res_high["final_units"] == 0.0

    res_valid = calculate_smart_units(ev_percent=7.5)
    assert res_valid["status"] == "APPROVED"
    assert res_valid["final_units"] == 1.0

def test_ai_veto():
    res_veto = calculate_smart_units(ev_percent=12.0, recommendation_adjustment="AVOID")
    assert res_veto["status"] == "VETOED_BY_AI"
    assert res_veto["final_units"] == 0.0

def test_over_vs_under_polarities():
    res_over_caution = calculate_smart_units(
        ev_percent=8.0, 
        side="over", 
        ai_multiplier=0.65, 
        recommendation_adjustment="CAUTION"
    )
    assert res_over_caution["status"] == "APPROVED"
    assert res_over_caution["final_units"] <= 0.75

    res_under_boost = calculate_smart_units(
        ev_percent=8.0, 
        side="under", 
        ai_multiplier=1.30, 
        recommendation_adjustment="BOOST"
    )
    assert res_under_boost["status"] == "APPROVED"
    assert res_under_boost["final_units"] == 1.25

def test_discretization_and_clamping():
    res_boost = calculate_smart_units(ev_percent=14.0, ai_multiplier=1.35, recommendation_adjustment="BOOST")
    assert res_boost["final_units"] == 1.75
    assert (res_boost["final_units"] * 4) % 1 == 0

def test_tail_penalty():
    res_normal = calculate_smart_units(ev_percent=8.0, z_distance=0.3)
    res_tail = calculate_smart_units(ev_percent=8.0, z_distance=1.8)
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
