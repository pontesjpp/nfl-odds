import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup
import polars as pl
import re
import os
import sys
import argparse

async def scrape_match(url: str):
    print(f"Scraping {url}...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        
        # Injeta modificações Stealth para contornar anti-bots (DataDome/Cloudflare)
        await Stealth().apply_stealth_async(page)
        
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            if response and response.status in [403, 429]:
                print(f"🚨 ANTI-BOT BLOQUEIOU O ACESSO (Status {response.status}) 🚨")
                await browser.close()
                return None
        except Exception as e:
            print(f"Navigation error: {e}")
            await browser.close()
            return None
            
        await page.wait_for_timeout(2000)
        
        # Verifica bloqueio ou captcha no título / conteúdo
        title = await page.title()
        if "datadome" in title.lower() or "blocked" in title.lower():
            print(f"🚨 ANTI-BOT BLOQUEIOU O ACESSO (Título: {title}) 🚨")
            await browser.close()
            return None
            
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
            await browser.close()
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
                await browser.close()
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
        await browser.close()
        
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
                    "bookmaker": "Betclic"
                })
            else:
                if "Touchdown" in market_name:
                    data.append({
                        "player_name": label_text.strip(),
                        "market": "anytime_td",
                        "side": "over",
                        "line": 0.5,
                        "odds": odd_val,
                        "bookmaker": "Betclic"
                    })
                    
    df = pl.DataFrame(data)
    
    if len(df) > 0:
        print(f"Loaded {len(df)} player props.")
    else:
        print("Warning: Scraped data is empty after navigating to 'Joueurs'. Anti-bot triggered or format changed.")
        
    return df

async def run_betclic_scraping(slow_mode: bool = True, links_file: str = "data/links.txt") -> pl.DataFrame:
    if not os.path.exists(links_file):
        print(f"Error: {links_file} not found. Please create it with Betclic URLs.")
        return pl.DataFrame()

    with open(links_file, "r") as f:
        links = [line.strip() for line in f if line.strip()]

    # Preserve original order while deduplicating
    links = list(dict.fromkeys(links))

    if not links:
        print(f"No links found in {links_file}")
        return pl.DataFrame()

    mode_text = "🐢 Slow Scrape (recomendado anti-bot: 30-60s de intervalo)" if slow_mode else "⚡ Fast Scrape (5-12s de intervalo)"
    print(f"Encontrados {len(links)} jogos únicos para raspar. Modo: {mode_text}")
    
    all_dfs = []
    
    for i, url in enumerate(links, 1):
        print(f"\n--- Processando jogo {i}/{len(links)} ---")
        try:
            df = await scrape_match(url)
            
            if df is None:
                print("🚨 Abortando jogos restantes devido a bloqueio do anti-bot para proteger seu IP.")
                break
                
            if not df.is_empty():
                all_dfs.append(df)
            else:
                print("Nenhum dado retornado para este jogo.")
        except Exception as e:
            print(f"Erro ao processar o jogo: {e}")
            
        if i < len(links):
            import random
            if slow_mode:
                wait_time = random.uniform(30.0, 60.0)
                print(f"🐢 Slow Scrape: Esperando {wait_time:.1f}s para simular leitura humana e proteger IP...")
            else:
                wait_time = random.uniform(5.0, 12.0)
                print(f"⚡ Fast Scrape: Esperando {wait_time:.1f}s para evitar bloqueio de IP...")
            await asyncio.sleep(wait_time)
            
    if all_dfs:
        final_df = pl.concat(all_dfs)
        os.makedirs("data", exist_ok=True)
        out_path = "data/betclic_parsed_odds.parquet"
        final_df.write_parquet(out_path)
        print(f"\n✅ Scraping concluído! Foram salvas {len(final_df)} props totais em '{out_path}'.")
        print("Agora você pode rodar: uv run python pipeline.py --live")
        return final_df
    else:
        print("\n❌ Nenhuma prop foi encontrada/raspada em nenhum jogo (mercados ainda fechados na Betclic).")
        return pl.DataFrame()

async def main():
    parser = argparse.ArgumentParser(description="Scraper de Player Props da Betclic")
    parser.add_argument("--fast", action="store_true", help="Executa no modo rápido (5-12s delay)")
    parser.add_argument("--slow", action="store_true", default=True, help="Executa no modo slow human-like (30-60s delay, padrão)")
    parser.add_argument("--links", default="data/links.txt", help="Caminho para arquivo de links")
    args = parser.parse_args()

    slow_mode = not args.fast
    await run_betclic_scraping(slow_mode=slow_mode, links_file=args.links)

if __name__ == "__main__":
    asyncio.run(main())
