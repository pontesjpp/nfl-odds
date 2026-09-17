import os
import tempfile
import polars as pl
import pytest
from nfl_odds.scraper.incremental import (
    MatchStatusType,
    YARDS_MARKETS,
    evaluate_match_status,
    extract_match_id,
    normalize_url,
    load_and_migrate_odds,
    save_consolidated_odds,
    upsert_match_odds,
)


@pytest.fixture
def sample_urls():
    return {
        "bills_lions": "https://www.betclic.fr/football-americain-samerican_football/nfl-c84/buffalo-bills-detroit-lions-m1114076329902080",
        "jets_packers": "https://www.betclic.fr/football-americain-samerican_football/nfl-c84/new-york-jets-green-bay-packers-m1218484161769472",
        "bears_vikings": "https://www.betclic.fr/football-americain-samerican_football/nfl-c84/chicago-bears-minnesota-vikings-m1218487277068288",
    }


def test_url_normalization_and_id_extraction(sample_urls):
    url = sample_urls["bills_lions"] + "  /  "
    norm = normalize_url(url)
    assert norm == sample_urls["bills_lions"]
    assert extract_match_id(url) == "m1114076329902080"


def test_scenario_1_unseen_game_should_scrape(sample_urls):
    url = sample_urls["jets_packers"]

    # 1a. None DataFrame
    status_none = evaluate_match_status(None, url)
    assert status_none.should_scrape is True
    assert status_none.is_complete is False
    assert status_none.status_type == MatchStatusType.NO_PREVIOUS_PROPS
    assert status_none.total_props == 0
    assert status_none.yards_props == 0

    # 1b. Empty DataFrame
    status_empty = evaluate_match_status(pl.DataFrame(), url)
    assert status_empty.should_scrape is True
    assert status_empty.is_complete is False
    assert status_empty.status_type == MatchStatusType.NO_PREVIOUS_PROPS

    # 1c. DataFrame has other games, but not this URL
    other_df = pl.DataFrame({
        "player_name": ["Josh Allen", "Josh Allen", "Josh Allen"],
        "market": ["passing_yards", "passing_yards", "anytime_td"],
        "side": ["over", "under", "over"],
        "line": [250.5, 250.5, 0.5],
        "odds": [1.85, 1.85, 2.10],
        "bookmaker": ["Betclic", "Betclic", "Betclic"],
        "match_url": [sample_urls["bills_lions"]] * 3,
        "match_id": ["m1114076329902080"] * 3,
    })
    status_other = evaluate_match_status(other_df, url)
    assert status_other.should_scrape is True
    assert status_other.is_complete is False
    assert status_other.status_type == MatchStatusType.NO_PREVIOUS_PROPS
    assert "sem odds prévias" in status_other.reason


def test_scenario_2_insufficient_props_should_rescrape(sample_urls):
    url = sample_urls["jets_packers"]
    match_id = extract_match_id(url)

    # Only 2 props captured (less than minimum 3)
    partial_df = pl.DataFrame({
        "player_name": ["Aaron Rodgers", "Aaron Rodgers"],
        "market": ["passing_yards", "passing_yards"],
        "side": ["over", "under"],
        "line": [235.5, 235.5],
        "odds": [1.85, 1.85],
        "bookmaker": ["Betclic", "Betclic"],
        "match_url": [url, url],
        "match_id": [match_id, match_id],
    })

    status = evaluate_match_status(partial_df, url)
    assert status.should_scrape is True
    assert status.is_complete is False
    assert status.status_type == MatchStatusType.INSUFFICIENT_PROPS
    assert status.total_props == 2
    assert status.yards_props == 2
    assert "< 3 necessárias" in status.reason


def test_scenario_3_no_yards_markets_should_rescrape(sample_urls):
    url = sample_urls["bears_vikings"]
    match_id = extract_match_id(url)

    # 4 props, but all are anytime_td ('Joueurs' tab open, but yards lines not posted yet)
    td_only_df = pl.DataFrame({
        "player_name": ["Caleb Williams", "DJ Moore", "Justin Jefferson", "Aaron Jones"],
        "market": ["anytime_td", "anytime_td", "anytime_td", "anytime_td"],
        "side": ["over", "over", "over", "over"],
        "line": [0.5, 0.5, 0.5, 0.5],
        "odds": [3.5, 2.8, 1.9, 2.1],
        "bookmaker": ["Betclic"] * 4,
        "match_url": [url] * 4,
        "match_id": [match_id] * 4,
    })

    status = evaluate_match_status(td_only_df, url)
    assert status.should_scrape is True
    assert status.is_complete is False
    assert status.status_type == MatchStatusType.NO_YARDS_MARKETS
    assert status.total_props == 4
    assert status.yards_props == 0
    assert "NENHUM mercado de jardas" in status.reason


def test_scenario_4_complete_game_should_skip(sample_urls):
    url = sample_urls["bills_lions"]
    match_id = extract_match_id(url)

    # 5 props, including passing, rushing, receiving yards and anytime_td
    complete_df = pl.DataFrame({
        "player_name": ["Josh Allen", "Josh Allen", "James Cook", "Amon-Ra St. Brown", "Jared Goff"],
        "market": ["passing_yards", "rushing_yards", "rushing_yards", "receiving_yards", "anytime_td"],
        "side": ["over", "over", "over", "over", "over"],
        "line": [260.5, 34.5, 62.5, 81.5, 0.5],
        "odds": [1.85, 1.85, 1.85, 1.85, 4.5],
        "bookmaker": ["Betclic"] * 5,
        "match_url": [url] * 5,
        "match_id": [match_id] * 5,
    })

    status = evaluate_match_status(complete_df, url)
    assert status.should_scrape is False
    assert status.is_complete is True
    assert status.status_type == MatchStatusType.COMPLETE
    assert status.total_props == 5
    assert status.yards_props == 4
    assert "já consolidada" in status.reason


def test_upsert_replaces_old_match_props_and_preserves_others(sample_urls):
    url1 = sample_urls["bills_lions"]
    url2 = sample_urls["jets_packers"]

    initial_df = pl.DataFrame({
        "player_name": ["Josh Allen", "Aaron Rodgers"],
        "market": ["passing_yards", "anytime_td"],
        "side": ["over", "over"],
        "line": [260.5, 0.5],
        "odds": [1.85, 4.0],
        "bookmaker": ["Betclic", "Betclic"],
        "match_url": [url1, url2],
        "match_id": [extract_match_id(url1), extract_match_id(url2)],
    })

    # Fresh scrape for Match 2 with yards lines now open
    new_match2_df = pl.DataFrame({
        "player_name": ["Aaron Rodgers", "Aaron Rodgers", "Breece Hall"],
        "market": ["passing_yards", "passing_yards", "rushing_yards"],
        "side": ["over", "under", "over"],
        "line": [238.5, 238.5, 64.5],
        "odds": [1.85, 1.85, 1.85],
        "bookmaker": ["Betclic", "Betclic", "Betclic"],
    })

    consolidated = upsert_match_odds(initial_df, new_match2_df, url2)

    # Match 1 (bills_lions) must still be preserved
    match1_rows = consolidated.filter(pl.col("match_url") == url1)
    assert len(match1_rows) == 1
    assert match1_rows["player_name"][0] == "Josh Allen"

    # Match 2 (jets_packers) old anytime_td must be replaced by new 3 rows
    match2_rows = consolidated.filter(pl.col("match_url") == url2)
    assert len(match2_rows) == 3
    assert "rushing_yards" in match2_rows["market"].to_list()
    assert "passing_yards" in match2_rows["market"].to_list()
    assert "anytime_td" not in match2_rows["market"].to_list()

    # Match status for Match 2 should now evaluate to COMPLETE!
    status2 = evaluate_match_status(consolidated, url2)
    assert status2.is_complete is True
    assert status2.should_scrape is False
    assert status2.status_type == MatchStatusType.COMPLETE


def test_atomic_parquet_save_and_load(tmp_path):
    parquet_file = str(tmp_path / "test_odds.parquet")
    df = pl.DataFrame({
        "player_name": ["Josh Allen", "James Cook", "Jahmyr Gibbs"],
        "market": ["passing_yards", "rushing_yards", "receiving_yards"],
        "side": ["over", "over", "over"],
        "line": [260.5, 62.5, 35.5],
        "odds": [1.85, 1.85, 1.85],
        "bookmaker": ["Betclic"] * 3,
        "match_url": ["https://betclic.fr/match-m1"] * 3,
        "match_id": ["m1"] * 3,
    })

    save_consolidated_odds(df, parquet_file)
    assert os.path.exists(parquet_file)
    assert not os.path.exists(parquet_file + ".tmp")

    loaded = pl.read_parquet(parquet_file)
    assert len(loaded) == 3
    assert loaded["player_name"].to_list() == ["Josh Allen", "James Cook", "Jahmyr Gibbs"]
