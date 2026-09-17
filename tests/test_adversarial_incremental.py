"""
Adversarial empirical stress tests for Smart Incremental Scraping & Atomic Parquet Persistence.
Module: src/nfl_odds/scraper/incremental.py
"""
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
def base_url():
    return "https://www.betclic.fr/football-americain-samerican_football/nfl-c84/buffalo-bills-detroit-lions-m1114076329902080"


@pytest.fixture
def second_url():
    return "https://www.betclic.fr/football-americain-samerican_football/nfl-c84/new-york-jets-green-bay-packers-m1218484161769472"


# =========================================================================
# Scenario 1: Zero Props -> NO_PREVIOUS_PROPS
# =========================================================================

def test_adversarial_zero_props_none_dataframe(base_url):
    """Case 1a: None DataFrame must yield NO_PREVIOUS_PROPS, should_scrape=True, is_complete=False."""
    status = evaluate_match_status(None, base_url)
    assert status.status_type == MatchStatusType.NO_PREVIOUS_PROPS
    assert status.should_scrape is True
    assert status.is_complete is False
    assert status.total_props == 0
    assert status.yards_props == 0
    assert "sem odds prévias" in status.reason


def test_adversarial_zero_props_empty_dataframe(base_url):
    """Case 1b: Empty DataFrame (0 cols, 0 rows) must yield NO_PREVIOUS_PROPS."""
    status = evaluate_match_status(pl.DataFrame(), base_url)
    assert status.status_type == MatchStatusType.NO_PREVIOUS_PROPS
    assert status.should_scrape is True
    assert status.is_complete is False
    assert status.total_props == 0
    assert status.yards_props == 0


def test_adversarial_zero_props_empty_with_schema(base_url):
    """Case 1c: Empty DataFrame with typed schema (0 rows) must yield NO_PREVIOUS_PROPS."""
    schema_df = pl.DataFrame(
        schema={
            "player_name": pl.Utf8,
            "market": pl.Utf8,
            "side": pl.Utf8,
            "line": pl.Float64,
            "odds": pl.Float64,
            "bookmaker": pl.Utf8,
            "match_url": pl.Utf8,
            "match_id": pl.Utf8,
        }
    )
    status = evaluate_match_status(schema_df, base_url)
    assert status.status_type == MatchStatusType.NO_PREVIOUS_PROPS
    assert status.should_scrape is True
    assert status.is_complete is False
    assert status.total_props == 0
    assert status.yards_props == 0


def test_adversarial_zero_props_unseen_game_with_other_games_present(base_url, second_url):
    """Case 1d: DataFrame populated with 50 props of game A, querying unseen game B."""
    other_df = pl.DataFrame({
        "player_name": [f"Player {i}" for i in range(50)],
        "market": ["passing_yards"] * 25 + ["rushing_yards"] * 25,
        "side": ["over"] * 50,
        "line": [250.5] * 50,
        "odds": [1.90] * 50,
        "bookmaker": ["Betclic"] * 50,
        "match_url": [base_url] * 50,
        "match_id": [extract_match_id(base_url)] * 50,
    })
    status = evaluate_match_status(other_df, second_url)
    assert status.status_type == MatchStatusType.NO_PREVIOUS_PROPS
    assert status.should_scrape is True
    assert status.is_complete is False
    assert status.total_props == 0
    assert status.yards_props == 0
    assert "sem odds prévias" in status.reason


# =========================================================================
# Scenario 2: 1-2 Props With Yards -> INSUFFICIENT_PROPS
# =========================================================================

@pytest.mark.parametrize("market_name", ["passing_yards", "rushing_yards", "receiving_yards"])
def test_adversarial_exactly_one_prop_with_yards(base_url, market_name):
    """Case 2a: Exactly 1 prop with yardage market must yield INSUFFICIENT_PROPS (< 3 required)."""
    df = pl.DataFrame({
        "player_name": ["Josh Allen"],
        "market": [market_name],
        "side": ["over"],
        "line": [260.5],
        "odds": [1.85],
        "bookmaker": ["Betclic"],
        "match_url": [base_url],
        "match_id": [extract_match_id(base_url)],
    })
    status = evaluate_match_status(df, base_url)
    assert status.status_type == MatchStatusType.INSUFFICIENT_PROPS
    assert status.should_scrape is True
    assert status.is_complete is False
    assert status.total_props == 1
    assert status.yards_props == 1
    assert "< 3 necessárias" in status.reason


def test_adversarial_exactly_two_props_both_yards(base_url):
    """Case 2b: Exactly 2 props both with yardage markets must yield INSUFFICIENT_PROPS."""
    df = pl.DataFrame({
        "player_name": ["Josh Allen", "James Cook"],
        "market": ["passing_yards", "rushing_yards"],
        "side": ["over", "over"],
        "line": [260.5, 65.5],
        "odds": [1.85, 1.85],
        "bookmaker": ["Betclic", "Betclic"],
        "match_url": [base_url, base_url],
        "match_id": [extract_match_id(base_url), extract_match_id(base_url)],
    })
    status = evaluate_match_status(df, base_url)
    assert status.status_type == MatchStatusType.INSUFFICIENT_PROPS
    assert status.should_scrape is True
    assert status.is_complete is False
    assert status.total_props == 2
    assert status.yards_props == 2
    assert "< 3 necessárias" in status.reason


def test_adversarial_exactly_two_props_one_td_one_yard(base_url):
    """Case 2c: Exactly 2 props (1 anytime_td + 1 receiving_yards) must yield INSUFFICIENT_PROPS."""
    df = pl.DataFrame({
        "player_name": ["Stefon Diggs", "Stefon Diggs"],
        "market": ["anytime_td", "receiving_yards"],
        "side": ["over", "over"],
        "line": [0.5, 70.5],
        "odds": [2.5, 1.85],
        "bookmaker": ["Betclic", "Betclic"],
        "match_url": [base_url, base_url],
        "match_id": [extract_match_id(base_url), extract_match_id(base_url)],
    })
    status = evaluate_match_status(df, base_url)
    assert status.status_type == MatchStatusType.INSUFFICIENT_PROPS
    assert status.should_scrape is True
    assert status.is_complete is False
    assert status.total_props == 2
    assert status.yards_props == 1
    assert "< 3 necessárias" in status.reason


# =========================================================================
# Scenario 3: 100 TD Props Without Yards -> NO_YARDS_MARKETS
# =========================================================================

def test_adversarial_100_props_anytime_td_zero_yards(base_url):
    """Case 3: 100 props of anytime_td and 0 yards lines must yield NO_YARDS_MARKETS."""
    match_id = extract_match_id(base_url)
    df = pl.DataFrame({
        "player_name": [f"Player {i}" for i in range(100)],
        "market": ["anytime_td"] * 100,
        "side": ["over"] * 100,
        "line": [0.5] * 100,
        "odds": [2.0 + (i * 0.05) for i in range(100)],
        "bookmaker": ["Betclic"] * 100,
        "match_url": [base_url] * 100,
        "match_id": [match_id] * 100,
    })
    status = evaluate_match_status(df, base_url)
    assert status.status_type == MatchStatusType.NO_YARDS_MARKETS
    assert status.should_scrape is True
    assert status.is_complete is False
    assert status.total_props == 100
    assert status.yards_props == 0
    assert "NENHUM mercado de jardas" in status.reason


def test_adversarial_multiple_non_yards_markets_zero_yards(base_url):
    """Case 3b: Props consisting of non-yardage markets (anytime_td, first_td, tackles) must yield NO_YARDS_MARKETS."""
    match_id = extract_match_id(base_url)
    df = pl.DataFrame({
        "player_name": ["Player A", "Player B", "Player C", "Player D"],
        "market": ["anytime_td", "first_td", "player_tackles", "interceptions"],
        "side": ["over"] * 4,
        "line": [0.5, 0.5, 4.5, 0.5],
        "odds": [2.1, 8.0, 1.85, 3.5],
        "bookmaker": ["Betclic"] * 4,
        "match_url": [base_url] * 4,
        "match_id": [match_id] * 4,
    })
    status = evaluate_match_status(df, base_url)
    assert status.status_type == MatchStatusType.NO_YARDS_MARKETS
    assert status.should_scrape is True
    assert status.is_complete is False
    assert status.total_props == 4
    assert status.yards_props == 0


# =========================================================================
# Scenario 4: Exact 3 Props Boundaries
# =========================================================================

def test_adversarial_exact_3_props_with_1_yard_complete(base_url):
    """Case 4a: Exact boundary: exactly 3 props (2 anytime_td + 1 passing_yards) -> COMPLETE."""
    match_id = extract_match_id(base_url)
    df = pl.DataFrame({
        "player_name": ["Player 1", "Player 2", "QB 1"],
        "market": ["anytime_td", "anytime_td", "passing_yards"],
        "side": ["over", "over", "over"],
        "line": [0.5, 0.5, 245.5],
        "odds": [2.5, 3.1, 1.85],
        "bookmaker": ["Betclic"] * 3,
        "match_url": [base_url] * 3,
        "match_id": [match_id] * 3,
    })
    status = evaluate_match_status(df, base_url)
    assert status.status_type == MatchStatusType.COMPLETE
    assert status.should_scrape is False
    assert status.is_complete is True
    assert status.total_props == 3
    assert status.yards_props == 1
    assert "já consolidada com 3 props" in status.reason


def test_adversarial_exact_3_props_with_0_yards_no_yards(base_url):
    """Case 4b: Exact boundary: exactly 3 props with 0 yards -> NO_YARDS_MARKETS."""
    match_id = extract_match_id(base_url)
    df = pl.DataFrame({
        "player_name": ["Player 1", "Player 2", "Player 3"],
        "market": ["anytime_td", "anytime_td", "anytime_td"],
        "side": ["over", "over", "over"],
        "line": [0.5, 0.5, 0.5],
        "odds": [2.5, 3.1, 4.0],
        "bookmaker": ["Betclic"] * 3,
        "match_url": [base_url] * 3,
        "match_id": [match_id] * 3,
    })
    status = evaluate_match_status(df, base_url)
    assert status.status_type == MatchStatusType.NO_YARDS_MARKETS
    assert status.should_scrape is True
    assert status.is_complete is False
    assert status.total_props == 3
    assert status.yards_props == 0


def test_adversarial_exact_3_props_all_3_yards_complete(base_url):
    """Case 4c: Exact boundary: exactly 3 props (passing, rushing, receiving) -> COMPLETE."""
    match_id = extract_match_id(base_url)
    df = pl.DataFrame({
        "player_name": ["QB 1", "RB 1", "WR 1"],
        "market": ["passing_yards", "rushing_yards", "receiving_yards"],
        "side": ["over", "over", "over"],
        "line": [245.5, 55.5, 62.5],
        "odds": [1.85, 1.85, 1.85],
        "bookmaker": ["Betclic"] * 3,
        "match_url": [base_url] * 3,
        "match_id": [match_id] * 3,
    })
    status = evaluate_match_status(df, base_url)
    assert status.status_type == MatchStatusType.COMPLETE
    assert status.should_scrape is False
    assert status.is_complete is True
    assert status.total_props == 3
    assert status.yards_props == 3


# =========================================================================
# Scenario 5: Parquet Persistence - Non-existent File
# =========================================================================

def test_adversarial_load_non_existent_parquet(tmp_path):
    """Case 5a: Non-existent parquet file returns empty DataFrame without raising exception."""
    missing_path = str(tmp_path / "does_not_exist" / "odds.parquet")
    df = load_and_migrate_odds(missing_path)
    assert isinstance(df, pl.DataFrame)
    assert df.is_empty()
    assert len(df) == 0


def test_adversarial_upsert_on_none_and_empty_consolidated(base_url):
    """Case 5b: Upsert on None or empty DataFrame initializes schema and adds metadata."""
    new_df = pl.DataFrame({
        "player_name": ["Josh Allen"],
        "market": ["passing_yards"],
        "side": ["over"],
        "line": [250.5],
        "odds": [1.85],
    })

    # None consolidated
    res_none = upsert_match_odds(None, new_df, base_url)
    assert len(res_none) == 1
    assert "match_url" in res_none.columns
    assert "match_id" in res_none.columns
    assert "scraped_at" in res_none.columns
    assert res_none["match_url"][0] == base_url
    assert res_none["match_id"][0] == extract_match_id(base_url)

    # Empty DataFrame consolidated
    res_empty = upsert_match_odds(pl.DataFrame(), new_df, base_url)
    assert len(res_empty) == 1
    assert res_empty["match_id"][0] == extract_match_id(base_url)


def test_adversarial_save_creates_parent_directories_atomically(tmp_path):
    """Case 5c: save_consolidated_odds creates non-existent parent dirs recursively."""
    deep_path = str(tmp_path / "level1" / "level2" / "level3" / "odds.parquet")
    df = pl.DataFrame({
        "player_name": ["Test"],
        "market": ["passing_yards"],
    })
    save_consolidated_odds(df, deep_path)
    assert os.path.exists(deep_path)
    assert not os.path.exists(deep_path + ".tmp")
    loaded = pl.read_parquet(deep_path)
    assert len(loaded) == 1


# =========================================================================
# Scenario 6: Parquet Persistence - Empty File
# =========================================================================

def test_adversarial_zero_byte_parquet_file(tmp_path):
    """Case 6a: 0-byte file must be caught gracefully and return empty DataFrame."""
    zero_byte_path = str(tmp_path / "zero_byte.parquet")
    with open(zero_byte_path, "wb") as f:
        pass  # 0 bytes
    assert os.path.getsize(zero_byte_path) == 0

    df = load_and_migrate_odds(zero_byte_path)
    assert isinstance(df, pl.DataFrame)
    assert df.is_empty()


def test_adversarial_valid_empty_parquet_file(tmp_path):
    """Case 6b: Valid parquet file with 0 rows must load cleanly without raising."""
    empty_parquet = str(tmp_path / "valid_empty.parquet")
    pl.DataFrame(schema={"player_name": pl.Utf8, "market": pl.Utf8}).write_parquet(empty_parquet)
    assert os.path.exists(empty_parquet)

    df = load_and_migrate_odds(empty_parquet)
    assert isinstance(df, pl.DataFrame)
    assert df.is_empty()


# =========================================================================
# Scenario 7: Parquet Persistence - Corrupted File
# =========================================================================

def test_adversarial_corrupted_garbage_parquet_file(tmp_path):
    """Case 7: Corrupted parquet file with random garbage bytes returns empty DataFrame."""
    corrupted_path = str(tmp_path / "corrupted.parquet")
    with open(corrupted_path, "wb") as f:
        f.write(b"PAR1\xff\xfe\x00\x01MALFORMED_HEADER_DATA_GARBAGE\x99\x88\x77\x66")

    df = load_and_migrate_odds(corrupted_path)
    assert isinstance(df, pl.DataFrame)
    assert df.is_empty()


# =========================================================================
# Scenario 8: Idempotency of Repeated Upserts
# =========================================================================

def test_adversarial_idempotency_repeated_exact_upserts(base_url, second_url):
    """Case 8a: Repeatedly upserting the exact same data must be strictly invariant in row count and content."""
    initial_df = pl.DataFrame({
        "player_name": ["Josh Allen", "James Cook"],
        "market": ["passing_yards", "rushing_yards"],
        "side": ["over", "over"],
        "line": [260.5, 65.5],
        "odds": [1.85, 1.85],
        "bookmaker": ["Betclic", "Betclic"],
        "match_url": [base_url, base_url],
        "match_id": [extract_match_id(base_url), extract_match_id(base_url)],
    })

    new_scrape = pl.DataFrame({
        "player_name": ["Aaron Rodgers", "Breece Hall", "Garrett Wilson"],
        "market": ["passing_yards", "rushing_yards", "receiving_yards"],
        "side": ["over", "over", "over"],
        "line": [235.5, 60.5, 72.5],
        "odds": [1.85, 1.85, 1.85],
        "bookmaker": ["Betclic", "Betclic", "Betclic"],
    })

    # First upsert
    step1 = upsert_match_odds(initial_df, new_scrape, second_url)
    assert len(step1) == 5

    # Repeat upsert 10 times with the exact same data
    curr = step1
    for _ in range(10):
        curr = upsert_match_odds(curr, new_scrape, second_url)
        assert len(curr) == 5

    # Check that game 1 props and game 2 props are intact
    g1 = curr.filter(pl.col("match_id") == extract_match_id(base_url))
    g2 = curr.filter(pl.col("match_id") == extract_match_id(second_url))
    assert len(g1) == 2
    assert len(g2) == 3


def test_adversarial_upsert_replaces_old_match_without_affecting_unrelated_matches(base_url, second_url):
    """Case 8b: Upserting an updated scrape for game 2 completely updates game 2 and leaves game 1 unchanged."""
    url3 = "https://www.betclic.fr/football-americain-samerican_football/nfl-c84/chicago-bears-minnesota-vikings-m1218487277068288"
    id3 = extract_match_id(url3)

    consolidated = pl.DataFrame({
        "player_name": ["Josh Allen", "Aaron Rodgers", "Caleb Williams"],
        "market": ["passing_yards", "anytime_td", "passing_yards"],
        "side": ["over", "over", "over"],
        "line": [260.5, 0.5, 215.5],
        "odds": [1.85, 4.0, 1.85],
        "bookmaker": ["Betclic", "Betclic", "Betclic"],
        "match_url": [base_url, second_url, url3],
        "match_id": [extract_match_id(base_url), extract_match_id(second_url), id3],
    })

    # Game 2 now gets 4 new props (replacing the single anytime_td)
    fresh_game2 = pl.DataFrame({
        "player_name": ["Aaron Rodgers", "Aaron Rodgers", "Breece Hall", "Garrett Wilson"],
        "market": ["passing_yards", "passing_yards", "rushing_yards", "receiving_yards"],
        "side": ["over", "under", "over", "over"],
        "line": [240.5, 240.5, 62.5, 68.5],
        "odds": [1.85, 1.85, 1.85, 1.85],
        "bookmaker": ["Betclic"] * 4,
    })

    updated = upsert_match_odds(consolidated, fresh_game2, second_url)
    assert len(updated) == 6  # 1 (game 1) + 4 (game 2) + 1 (game 3)

    # Game 1 preserved
    assert len(updated.filter(pl.col("match_id") == extract_match_id(base_url))) == 1
    # Game 3 preserved
    assert len(updated.filter(pl.col("match_id") == id3)) == 1
    # Game 2 updated
    g2 = updated.filter(pl.col("match_id") == extract_match_id(second_url))
    assert len(g2) == 4
    assert "anytime_td" not in g2["market"].to_list()


# =========================================================================
# Scenario 9: URL Permutations, Trailing Characters & ID Extraction
# =========================================================================

@pytest.mark.parametrize("suffix", ["/", "///", "  ", "\t", "/   ", "  /  "])
def test_adversarial_url_normalization_with_whitespace_and_slashes(base_url, suffix):
    """Case 9a: URLs with diverse trailing slashes and whitespace normalize identically."""
    dirty_url = base_url + suffix
    clean = normalize_url(dirty_url)
    assert clean == base_url
    assert extract_match_id(dirty_url) == extract_match_id(base_url)


def test_adversarial_evaluate_match_status_url_normalization_match(base_url):
    """Case 9b: evaluate_match_status succeeds when existing_df has dirty URL but query URL is clean, and vice-versa."""
    dirty_stored_url = base_url + " / \t"
    clean_query_url = base_url

    df = pl.DataFrame({
        "player_name": ["Josh Allen", "James Cook", "Stefon Diggs"],
        "market": ["passing_yards", "rushing_yards", "receiving_yards"],
        "side": ["over", "over", "over"],
        "line": [250.5, 60.5, 75.5],
        "odds": [1.85, 1.85, 1.85],
        "bookmaker": ["Betclic"] * 3,
        "match_url": [dirty_stored_url] * 3,
        "match_id": [extract_match_id(base_url)] * 3,
    })

    # Query with clean URL
    status = evaluate_match_status(df, clean_query_url)
    assert status.status_type == MatchStatusType.COMPLETE
    assert status.is_complete is True
    assert status.should_scrape is False

    # Query with dirty URL
    dirty_query = base_url + "///"
    status_dirty = evaluate_match_status(df, dirty_query)
    assert status_dirty.status_type == MatchStatusType.COMPLETE
    assert status_dirty.is_complete is True


# =========================================================================
# Scenario 10: Atomic File Persistence Safety
# =========================================================================

def test_adversarial_atomic_save_replaces_existing_cleanly(tmp_path):
    """Case 10: Atomic save safely replaces existing parquet file without leaving .tmp files."""
    dest = str(tmp_path / "odds.parquet")
    df1 = pl.DataFrame({"a": [1, 2, 3]})
    save_consolidated_odds(df1, dest)
    assert os.path.exists(dest)
    assert not os.path.exists(dest + ".tmp")
    assert len(pl.read_parquet(dest)) == 3

    # Overwrite with updated df
    df2 = pl.DataFrame({"a": [10, 20, 30, 40, 50]})
    save_consolidated_odds(df2, dest)
    assert os.path.exists(dest)
    assert not os.path.exists(dest + ".tmp")
    loaded = pl.read_parquet(dest)
    assert len(loaded) == 5
    assert loaded["a"].to_list() == [10, 20, 30, 40, 50]


# =========================================================================
# Scenario 11: Comprehensive Props x Yards Boundary Matrix
# =========================================================================

@pytest.mark.parametrize(
    "total_props,yards_props,expected_type,expected_scrape,expected_complete",
    [
        (0, 0, MatchStatusType.NO_PREVIOUS_PROPS, True, False),
        (1, 0, MatchStatusType.INSUFFICIENT_PROPS, True, False),
        (1, 1, MatchStatusType.INSUFFICIENT_PROPS, True, False),
        (2, 0, MatchStatusType.INSUFFICIENT_PROPS, True, False),
        (2, 1, MatchStatusType.INSUFFICIENT_PROPS, True, False),
        (2, 2, MatchStatusType.INSUFFICIENT_PROPS, True, False),
        (3, 0, MatchStatusType.NO_YARDS_MARKETS, True, False),
        (3, 1, MatchStatusType.COMPLETE, False, True),
        (3, 2, MatchStatusType.COMPLETE, False, True),
        (3, 3, MatchStatusType.COMPLETE, False, True),
        (4, 0, MatchStatusType.NO_YARDS_MARKETS, True, False),
        (4, 1, MatchStatusType.COMPLETE, False, True),
        (20, 0, MatchStatusType.NO_YARDS_MARKETS, True, False),
        (20, 5, MatchStatusType.COMPLETE, False, True),
    ],
)
def test_adversarial_boundary_matrix(
    base_url, total_props, yards_props, expected_type, expected_scrape, expected_complete
):
    """Verifies the complete truth table for total_props x yards_props boundary conditions."""
    match_id = extract_match_id(base_url)
    if total_props == 0:
        df = pl.DataFrame()
    else:
        td_count = total_props - yards_props
        markets = ["anytime_td"] * td_count + ["passing_yards"] * yards_props
        df = pl.DataFrame({
            "player_name": [f"Player {i}" for i in range(total_props)],
            "market": markets,
            "side": ["over"] * total_props,
            "line": [0.5 if m == "anytime_td" else 200.5 for m in markets],
            "odds": [1.90] * total_props,
            "bookmaker": ["Betclic"] * total_props,
            "match_url": [base_url] * total_props,
            "match_id": [match_id] * total_props,
        })

    status = evaluate_match_status(df, base_url)
    assert status.status_type == expected_type
    assert status.should_scrape is expected_scrape
    assert status.is_complete is expected_complete
    assert status.total_props == total_props
    assert status.yards_props == yards_props


# =========================================================================
# Scenario 12: Schema Degradation & Missing Metadata Columns
# =========================================================================

def test_adversarial_missing_match_url_column_fallback_to_match_id(base_url):
    """Case 12a: If match_url is missing, evaluate_match_status must filter on match_id."""
    match_id = extract_match_id(base_url)
    df = pl.DataFrame({
        "player_name": ["Player 1", "Player 2", "Player 3"],
        "market": ["anytime_td", "passing_yards", "rushing_yards"],
        "side": ["over"] * 3,
        "line": [0.5, 250.5, 60.5],
        "odds": [1.85] * 3,
        "bookmaker": ["Betclic"] * 3,
        "match_id": [match_id] * 3,  # NO match_url column
    })

    status = evaluate_match_status(df, base_url)
    assert status.status_type == MatchStatusType.COMPLETE
    assert status.is_complete is True
    assert status.total_props == 3
    assert status.yards_props == 2


def test_adversarial_missing_both_match_url_and_match_id(base_url):
    """Case 12b: If both match_url and match_id are missing, returns NO_PREVIOUS_PROPS safely."""
    df = pl.DataFrame({
        "player_name": ["Player 1", "Player 2", "Player 3"],
        "market": ["anytime_td", "passing_yards", "rushing_yards"],
        "side": ["over"] * 3,
        "line": [0.5, 250.5, 60.5],
        "odds": [1.85] * 3,
        "bookmaker": ["Betclic"] * 3,
        # Neither match_url nor match_id
    })

    status = evaluate_match_status(df, base_url)
    assert status.status_type == MatchStatusType.NO_PREVIOUS_PROPS
    assert status.should_scrape is True
    assert status.is_complete is False
    assert status.total_props == 0


def test_adversarial_deduplication_inside_upsert(base_url):
    """Case 12c: upsert_match_odds deduplicates exact duplicate selections when consolidated_df exists."""
    existing_df = pl.DataFrame({
        "player_name": ["Other Player"],
        "market": ["passing_yards"],
        "side": ["over"],
        "line": [200.0],
        "odds": [1.90],
        "bookmaker": ["Betclic"],
        "match_url": ["https://betclic.fr/other-m999"],
        "match_id": ["m999"],
    })

    # new_df has identical row duplicated 3 times
    new_df = pl.DataFrame({
        "player_name": ["Josh Allen", "Josh Allen", "Josh Allen"],
        "market": ["passing_yards", "passing_yards", "passing_yards"],
        "side": ["over", "over", "over"],
        "line": [260.5, 260.5, 260.5],
        "odds": [1.85, 1.85, 1.85],
        "bookmaker": ["Betclic", "Betclic", "Betclic"],
    })

    # When consolidated_df exists, unique(subset=dedup_cols) dedupes the 3 new rows into 1
    merged = upsert_match_odds(existing_df, new_df, base_url)
    assert len(merged) == 2  # 1 other player + 1 unique Josh Allen
    allen_rows = merged.filter(pl.col("player_name") == "Josh Allen")
    assert len(allen_rows) == 1


def test_adversarial_live_dataset_links_evaluation():
    """Case 12d: Verify against the real repository files data/betclic_parsed_odds.parquet and data/links.txt."""
    parquet_path = "data/betclic_parsed_odds.parquet"
    links_path = "data/links.txt"
    if not os.path.exists(parquet_path) or not os.path.exists(links_path):
        pytest.skip("Live data files not present in workspace")

    df = load_and_migrate_odds(parquet_path, links_path)
    with open(links_path, "r") as f:
        links = [line.strip() for line in f if line.strip()]

    assert len(links) >= 1

    # First link must be complete Bills vs Lions
    first_status = evaluate_match_status(df, links[0])
    assert first_status.is_complete is True
    assert first_status.should_scrape is False
    assert first_status.status_type == MatchStatusType.COMPLETE
    assert first_status.total_props >= 3
    assert first_status.yards_props > 0

    # If there are subsequent links not yet scraped, they must require scraping
    for link in links[1:]:
        st = evaluate_match_status(df, link)
        assert st.should_scrape is True
        assert st.is_complete is False
        assert st.status_type == MatchStatusType.NO_PREVIOUS_PROPS

