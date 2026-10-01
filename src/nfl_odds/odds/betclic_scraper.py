import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup
import polars as pl
import re
import os
import sys
import argparse
from datetime import datetime
from typing import Optional, Any

from nfl_odds.scraper.incremental import (
    MatchStatus,
    MatchStatusType,
    YARDS_MARKETS,
    evaluate_match_status,
    extract_match_id,
    normalize_url,
    load_and_migrate_odds,
    save_consolidated_odds,
    upsert_match_odds,
)

async def _extract_match_props_from_page(page, url: str) -> Optional[pl.DataFrame]:
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        if response and response.status in [403, 429]:
            print(f"🚨 ANTI-BOT BLOQUEIOU O ACESSO (Status {response.status}) 🚨")
            return None
    except Exception as e:
        print(f"Navigation error: {e}")
        return None

    await page.wait_for_timeout(2000)

    # Verifica bloqueio ou captcha no título / conteúdo
    try:
        title = await page.title()
        if "datadome" in title.lower() or "blocked" in title.lower():
            print(f"🚨 ANTI-BOT BLOQUEIOU O ACESSO (Título: {title}) 🚨")
            return None
    except Exception:
        pass

    # 1. Bypass any overlays / cookie banners (TrustCommander / Didomi / generic)
    try:
        await page.evaluate("""() => {
            const selectors = [
                '#tc-privacy-wrapper', '.tc-privacy-wrapper', '#popin_tc_privacy',
                '#didomi-host', 'div[class*="overlay"]', 'div[class*="backdrop"]',
                '[id*="privacy"]', '[class*="privacy"]'
            ];
            for (const s of selectors) {
                document.querySelectorAll(s).forEach(el => el.remove());
            }
            document.body.style.overflow = 'auto';
        }""")
    except Exception:
        pass

    # 2. Check if 'Joueurs' tab exists organically
    joueurs_tab = page.locator('span.tab_label', has_text=re.compile(r'^Joueurs$', re.IGNORECASE)).or_(
        page.get_by_text("Joueurs", exact=True)
    ).first

    has_joueurs = False
    try:
        count = await joueurs_tab.count()
        if count > 0 and await joueurs_tab.is_visible():
            has_joueurs = True
    except Exception:
        has_joueurs = False

    if not has_joueurs:
        print("ℹ️ Aba 'Joueurs' não encontrada neste jogo (props de jogadores ainda não abertas pela Betclic).")
        return pl.DataFrame()

    print("Navigating to 'Joueurs' tab...")
    try:
        await joueurs_tab.scroll_into_view_if_needed(timeout=2500)
        await joueurs_tab.click(force=True, timeout=3000)
    except Exception:
        try:
            await joueurs_tab.evaluate("el => el.click()")
        except Exception as e:
            print(f"Error clicking tab: {e}")
            return pl.DataFrame()

    # Wait for markets to load
    for _ in range(15):
        await page.wait_for_timeout(500)
        count = await page.locator('.marketBox').count()
        if count > 15:
            break

    await page.wait_for_timeout(1000)

    # 3. Expand all 'see more' / 'afficher plus' buttons
    try:
        see_more_btns = page.locator('button.is-seeMore')
        count = await see_more_btns.count()
        if count > 0:
            print(f"Found {count} 'See More' buttons. Clicking them...")
            for i in range(count):
                try:
                    await see_more_btns.nth(i).click(force=True, timeout=1500)
                    await page.wait_for_timeout(200)
                except Exception:
                    pass
    except Exception as e:
        print(f"Error expanding 'See More' buttons: {e}")

    await page.wait_for_timeout(1000)

    # 4. Extract HTML state
    html = await page.content()

    # Parse the HTML using BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    markets = soup.select('.marketBox')

    data = []

    for m in markets:
        head = m.select_one('.marketBox_head')
        if not head:
            continue

        market_name = head.get_text(strip=True)

        # Filter for player props only
        if "Yards" not in market_name and "Touchdown" not in market_name:
            continue

        selections = m.select('.marketBox_lineSelection')
        for sel in selections:
            label = sel.select_one('.marketBox_label')
            if not label:
                continue

            label_text = label.get_text(strip=True)

            btn = sel.select_one('bcdk-bet-button-odds-animated')
            odd_str = btn.get_text(strip=True).replace(',', '.') if btn else "1.85"
            try:
                odd_val = float(odd_str)
            except ValueError:
                odd_val = 1.85

            match = re.match(r'(.+) ([+-]) de ([\d,]+)', label_text)
            if match:
                player = match.group(1).strip()
                side_str = match.group(2)
                side = "over" if side_str == "+" else "under"
                line_val = float(match.group(3).replace(',', '.'))

                market_type = ""
                if "réception" in market_name: market_type = "receiving_yards"
                elif "passe" in market_name: market_type = "passing_yards"
                elif "course" in market_name: market_type = "rushing_yards"

                data.append({
                    "player_name": player,
                    "market": market_type,
                    "side": side,
                    "line": line_val,
                    "odds": odd_val,
                    "bookmaker": "Betclic",
                    "match_url": normalize_url(url),
                    "match_id": extract_match_id(url),
                    "scraped_at": datetime.now().isoformat(),
                })
            else:
                if "Touchdown" in market_name:
                    data.append({
                        "player_name": label_text.strip(),
                        "market": "anytime_td",
                        "side": "over",
                        "line": 0.5,
                        "odds": odd_val,
                        "bookmaker": "Betclic",
                        "match_url": normalize_url(url),
                        "match_id": extract_match_id(url),
                        "scraped_at": datetime.now().isoformat(),
                    })

    df = pl.DataFrame(data)

    if len(df) > 0:
        dedup_cols = [c for c in ["player_name", "market", "side", "line"] if c in df.columns]
        df = df.unique(subset=dedup_cols)
        print(f"Loaded {len(df)} player props.")
    else:
        print("Warning: Scraped data is empty after navigating to 'Joueurs'. Anti-bot triggered or format changed.")

    return df

async def scrape_match(url: str, page: Optional[Any] = None) -> Optional[pl.DataFrame]:
    print(f"Scraping {url}...")
    if page is not None:
        return await _extract_match_props_from_page(page, url)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        local_page = await context.new_page()
        await Stealth().apply_stealth_async(local_page)
        res = await _extract_match_props_from_page(local_page, url)
        await browser.close()
        return res

async def run_betclic_scraping(
    slow_mode: bool = True,
    links_file: str = "data/links.txt",
    force_rescrape: bool = False,
) -> pl.DataFrame:
    if not os.path.exists(links_file):
        print(f"Error: {links_file} not found. Please create it with Betclic URLs.")
        return pl.DataFrame()

    with open(links_file, "r") as f:
        links = [normalize_url(line) for line in f if line.strip()]

    # Preserve original order while deduplicating
    links = list(dict.fromkeys(links))

    if not links:
        print(f"No links found in {links_file}")
        return pl.DataFrame()

    out_path = "data/betclic_parsed_odds.parquet"
    consolidated_df = load_and_migrate_odds(out_path, links_file)

    mode_text = "🐢 Slow Scrape (recomendado anti-bot: 20-40s de intervalo)" if slow_mode else "⚡ Fast Scrape (4-8s de intervalo)"
    print(f"Encontrados {len(links)} jogos únicos para avaliar. Modo: {mode_text}")
    print(f"Base de dados inicial contém {len(consolidated_df)} props consolidadas.")

    matches_to_scrape = []
    for i, url in enumerate(links, 1):
        status = evaluate_match_status(consolidated_df, url)
        if status.should_scrape or force_rescrape:
            matches_to_scrape.append((i, url, status))
        else:
            print(f"⏩ [SKIP] [{i}/{len(links)}] {status.reason}")

    skipped_count = len(links) - len(matches_to_scrape)
    scraped_count = 0

    if not matches_to_scrape:
        print("Todas as partidas já estão completas e consolidadas!")
        return consolidated_df

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        # Warm-up de sessão na página de NFL para estabelecer cookies e tokens DataDome
        try:
            print("🏈 Inicializando sessão persistente na Betclic NFL...")
            await page.goto(
                "https://www.betclic.fr/football-americain-samerican_football/nfl-c84",
                wait_until="domcontentloaded",
                timeout=25000,
            )
            await page.wait_for_timeout(2000)
            try:
                await page.evaluate("""() => {
                    const selectors = [
                        '#tc-privacy-wrapper', '.tc-privacy-wrapper', '#popin_tc_privacy',
                        '#didomi-host', 'div[class*="overlay"]', 'div[class*="backdrop"]',
                        '[id*="privacy"]', '[class*="privacy"]'
                    ];
                    for (const s of selectors) {
                        document.querySelectorAll(s).forEach(el => el.remove());
                    }
                    document.body.style.overflow = 'auto';
                }""")
            except Exception:
                pass
        except Exception as e:
            print(f"Warning na inicialização da sessão: {e}")

        for idx, (i, url, status) in enumerate(matches_to_scrape, 1):
            print(f"\n--- [{i}/{len(links)}] Processando: {status.reason} ---")
            scraped_count += 1

            try:
                df = await scrape_match(url, page=page)

                if df is None:
                    print("🚨 Abortando jogos restantes devido a bloqueio do anti-bot para proteger seu IP.")
                    break

                if not df.is_empty():
                    consolidated_df = upsert_match_odds(consolidated_df, df, url)
                    save_consolidated_odds(consolidated_df, out_path)
                    print(f"💾 Consolidado jogo no parquet ({len(df)} props captadas). Total no banco: {len(consolidated_df)} props.")
                else:
                    print("ℹ️ Nenhum dado retornado para este jogo no momento.")
            except Exception as e:
                print(f"Erro ao processar o jogo: {e}")

            if idx < len(matches_to_scrape):
                import random
                if slow_mode:
                    wait_time = random.uniform(20.0, 40.0)
                    print(f"🐢 Slow Scrape: Esperando {wait_time:.1f}s para simular leitura humana e proteger IP...")
                else:
                    wait_time = random.uniform(4.0, 8.0)
                    print(f"⚡ Fast Scrape: Esperando {wait_time:.1f}s para evitar bloqueio de IP...")
                await asyncio.sleep(wait_time)

        await browser.close()

    print(f"\n📊 Resumo da Execução:")
    print(f"   Total de partidas avaliadas: {len(links)}")
    print(f"   Partidas puladas (já completas): {skipped_count}")
    print(f"   Partidas raspadas/reprocessadas: {scraped_count}")
    print(f"   Total de props consolidadas: {len(consolidated_df)}")
    if len(consolidated_df) > 0:
        print(f"Arquivo salvo com sucesso em '{out_path}'.")
        print("Agora você pode rodar: uv run python pipeline.py --live")
    return consolidated_df

async def main():
    parser = argparse.ArgumentParser(description="Scraper de Player Props da Betclic")
    parser.add_argument("--fast", action="store_true", help="Executa no modo rápido (4-8s delay)")
    parser.add_argument("--slow", action="store_true", default=True, help="Executa no modo slow human-like (20-40s delay, padrão)")
    parser.add_argument("--force", action="store_true", help="Força re-raspagem mesmo de jogos completos")
    parser.add_argument("--links", default="data/links.txt", help="Caminho para arquivo de links")
    args = parser.parse_args()

    slow_mode = not args.fast
    await run_betclic_scraping(slow_mode=slow_mode, links_file=args.links, force_rescrape=args.force)

if __name__ == "__main__":
    asyncio.run(main())
