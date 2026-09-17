from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Set
import polars as pl

YARDS_MARKETS: Set[str] = {"passing_yards", "rushing_yards", "receiving_yards"}


class MatchStatusType(str, Enum):
    COMPLETE = "COMPLETE"
    NO_PREVIOUS_PROPS = "NO_PREVIOUS_PROPS"
    INSUFFICIENT_PROPS = "INSUFFICIENT_PROPS"
    NO_YARDS_MARKETS = "NO_YARDS_MARKETS"


@dataclass
class MatchStatus:
    url: str
    match_id: str
    total_props: int
    yards_props: int
    is_complete: bool
    should_scrape: bool
    status_type: MatchStatusType
    reason: str


def normalize_url(url: str) -> str:
    """Normalizes URL by stripping whitespace and trailing slashes."""
    cleaned = url.strip()
    while cleaned.endswith(("/", " ", "\t")):
        cleaned = cleaned.rstrip("/ \t")
    return cleaned


def extract_match_id(url: str) -> str:
    """Extracts the Betclic match ID (e.g. m1114076329902080) from a match URL."""
    cleaned = normalize_url(url)
    m = re.search(r'-(m\d+)', cleaned)
    if m:
        return m.group(1)
    m = re.search(r'(m\d{6,})', cleaned)
    if m:
        return m.group(1)
    return cleaned.split("/")[-1]


def evaluate_match_status(existing_df: Optional[pl.DataFrame], url: str) -> MatchStatus:
    """
    Evaluates whether a match is completely scraped or needs to be scraped/re-scraped.

    Rules:
    - Rule 1 (Complete): >= 3 props AND presence of yardage markets (passing_yards, rushing_yards, receiving_yards).
    - Rule 2 (Re-scrape): < 3 props OR only touchdown/joueurs props without yards lines.
    - Rule 3 (Skip): Complete games are marked is_complete=True and should_scrape=False.
    """
    norm_url = normalize_url(url)
    match_id = extract_match_id(url)

    if existing_df is None or existing_df.is_empty():
        return MatchStatus(
            url=norm_url,
            match_id=match_id,
            total_props=0,
            yards_props=0,
            is_complete=False,
            should_scrape=True,
            status_type=MatchStatusType.NO_PREVIOUS_PROPS,
            reason=f"Partida nova sem odds prévias: {match_id}",
        )

    # Filter for props matching this game by match_url or match_id
    if "match_url" in existing_df.columns:
        match_props = existing_df.filter(
            (pl.col("match_url").str.strip_chars().str.strip_chars_end("/") == norm_url)
            | (
                (pl.col("match_id") == match_id)
                if "match_id" in existing_df.columns
                else pl.lit(False)
            )
        )
    elif "match_id" in existing_df.columns:
        match_props = existing_df.filter(pl.col("match_id") == match_id)
    else:
        # If neither column exists yet in existing_df
        match_props = pl.DataFrame()

    total_props = len(match_props)

    if total_props == 0:
        return MatchStatus(
            url=norm_url,
            match_id=match_id,
            total_props=0,
            yards_props=0,
            is_complete=False,
            should_scrape=True,
            status_type=MatchStatusType.NO_PREVIOUS_PROPS,
            reason=f"Partida nova sem odds prévias: {match_id}",
        )

    yards_props = len(
        match_props.filter(pl.col("market").is_in(list(YARDS_MARKETS)))
    )

    # Rule 1 & 3: Complete if >= 3 props AND at least one yardage market exists
    if total_props >= 3 and yards_props > 0:
        return MatchStatus(
            url=norm_url,
            match_id=match_id,
            total_props=total_props,
            yards_props=yards_props,
            is_complete=True,
            should_scrape=False,
            status_type=MatchStatusType.COMPLETE,
            reason=f"Partida {match_id} já consolidada com {total_props} props (incluindo {yards_props} mercados de jardas).",
        )

    # Rule 2: < 3 props
    if total_props < 3:
        return MatchStatus(
            url=norm_url,
            match_id=match_id,
            total_props=total_props,
            yards_props=yards_props,
            is_complete=False,
            should_scrape=True,
            status_type=MatchStatusType.INSUFFICIENT_PROPS,
            reason=f"Partida {match_id} incompleta com apenas {total_props} props (< 3 necessárias). Re-raspando...",
        )

    # Rule 2: >= 3 props but 0 yards markets (e.g. only anytime_td / Joueurs)
    return MatchStatus(
        url=norm_url,
        match_id=match_id,
        total_props=total_props,
        yards_props=0,
        is_complete=False,
        should_scrape=True,
        status_type=MatchStatusType.NO_YARDS_MARKETS,
        reason=f"Partida {match_id} possui {total_props} props mas NENHUM mercado de jardas ({', '.join(sorted(YARDS_MARKETS))}). Re-raspando...",
    )


def load_and_migrate_odds(
    path: str = "data/betclic_parsed_odds.parquet",
    links_file: str = "data/links.txt",
) -> pl.DataFrame:
    """
    Loads existing odds parquet and migrates schema if match_url/match_id/scraped_at are missing.
    """
    if not os.path.exists(path):
        return pl.DataFrame()

    try:
        df = pl.read_parquet(path)
    except Exception as e:
        print(f"Warning: Could not read {path}: {e}")
        return pl.DataFrame()

    if df.is_empty():
        return df

    cols_to_add = []
    if "match_url" not in df.columns:
        first_url = "https://www.betclic.fr/football-americain-samerican_football/nfl-c84/buffalo-bills-detroit-lions-m1114076329902080"
        if os.path.exists(links_file):
            try:
                with open(links_file, "r") as f:
                    first_line = f.readline().strip()
                    if first_line:
                        first_url = first_line
            except Exception:
                pass
        norm_url = normalize_url(first_url)
        match_id = extract_match_id(first_url)
        cols_to_add.append(pl.lit(norm_url).alias("match_url"))
        cols_to_add.append(pl.lit(match_id).alias("match_id"))

    if "scraped_at" not in df.columns:
        cols_to_add.append(pl.lit(datetime.now().isoformat()).alias("scraped_at"))

    if cols_to_add:
        df = df.with_columns(cols_to_add)

    return df


def upsert_match_odds(
    consolidated_df: Optional[pl.DataFrame],
    new_df: pl.DataFrame,
    url: str,
) -> pl.DataFrame:
    """
    Atomically merges newly scraped odds for a match into the consolidated DataFrame,
    replacing previous entries for that match without dropping or duplicating others.
    """
    norm_url = normalize_url(url)
    match_id = extract_match_id(url)

    # Ensure new_df has metadata columns
    if not new_df.is_empty():
        cols_to_add = []
        if "match_url" not in new_df.columns:
            cols_to_add.append(pl.lit(norm_url).alias("match_url"))
        if "match_id" not in new_df.columns:
            cols_to_add.append(pl.lit(match_id).alias("match_id"))
        if "scraped_at" not in new_df.columns:
            cols_to_add.append(pl.lit(datetime.now().isoformat()).alias("scraped_at"))
        if cols_to_add:
            new_df = new_df.with_columns(cols_to_add)

    if consolidated_df is None or consolidated_df.is_empty():
        return new_df

    # Filter out existing rows for this match
    if "match_url" in consolidated_df.columns:
        filtered_df = consolidated_df.filter(
            (pl.col("match_url").str.strip_chars().str.strip_chars_end("/") != norm_url)
            & (
                (pl.col("match_id") != match_id)
                if "match_id" in consolidated_df.columns
                else pl.lit(True)
            )
        )
    elif "match_id" in consolidated_df.columns:
        filtered_df = consolidated_df.filter(pl.col("match_id") != match_id)
    else:
        filtered_df = consolidated_df

    if new_df.is_empty():
        return filtered_df

    merged = pl.concat([filtered_df, new_df], how="diagonal_relaxed")
    # Deduplicate
    dedup_cols = [
        c
        for c in ["player_name", "market", "side", "line", "match_id"]
        if c in merged.columns
    ]
    if not dedup_cols:
        dedup_cols = ["player_name", "market", "side", "line"]

    return merged.unique(subset=dedup_cols)


def save_consolidated_odds(
    df: pl.DataFrame,
    path: str = "data/betclic_parsed_odds.parquet",
) -> None:
    """
    Saves consolidated DataFrame to parquet atomically using a temporary file and os.replace.
    """
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    tmp_path = path + ".tmp"
    df.write_parquet(tmp_path)
    os.replace(tmp_path, path)
