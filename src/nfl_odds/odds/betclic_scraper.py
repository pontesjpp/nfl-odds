import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup
import polars as pl
import re
import os

async def scrape_match(url: str):
    print(f"Scraping {url}...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        # Injeta modificações Stealth para contornar anti-bots (DataDome/Cloudflare)
        await Stealth().apply_stealth_async(page)
        
        try:
            response = await page.goto(url, wait_until="domcontentloaded")
            if response and response.status in [403, 429]:
                print(f"🚨 ANTI-BOT BLOQUEIOU O ACESSO (Status {response.status}) 🚨")
                await browser.close()
                return None
        except Exception as e:
            print(f"Navigation error: {e}")
            await browser.close()
            return None
            
        await page.wait_for_timeout(2000)
        
        # 1. Bypass any overlays/cookie banners
        try:
            await page.evaluate("""
                document.querySelectorAll('div[class*="overlay"], div[class*="backdrop"], [id*="privacy"]').forEach(el => el.remove());
            """)
        except Exception:
            pass
            
        # 2. Click the Joueurs tab organically
        print("Navigating to 'Joueurs' tab...")
        try:
            tab = page.get_by_text("Joueurs", exact=True)
            await tab.scroll_into_view_if_needed(timeout=5000)
            await tab.click(timeout=5000)
            
            # Wait for markets to load
            for _ in range(10):
                await page.wait_for_timeout(1000)
                count = await page.locator('.marketBox').count()
                if count > 15:
                    break
                    
        except Exception as e:
            print(f"Error clicking tab: {e}")
            
        await page.wait_for_timeout(3000)
        
        # 3. Expand all 'see more' / 'afficher plus' buttons
        print("Expanding all 'See More' player lists...")
        try:
            see_more_btns = page.locator('button.is-seeMore')
            count = await see_more_btns.count()
            if count > 0:
                print(f"Found {count} 'See More' buttons. Clicking them...")
                for i in range(count):
                    try:
                        await see_more_btns.nth(i).scroll_into_view_if_needed(timeout=2000)
                        await see_more_btns.nth(i).click(timeout=3000)
                        await page.wait_for_timeout(300)
                    except Exception as e:
                        pass
        except Exception as e:
            print(f"Error expanding 'See More' buttons: {e}")
            
        await page.wait_for_timeout(3000)
        
        # 4. Extract the HTML state
        html = await page.content()
        await browser.close()
        
    # 4. Parse the HTML using BeautifulSoup
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
            # The player name is usually in the label
            label = sel.select_one('.marketBox_label')
            if not label:
                continue
                
            label_text = label.get_text(strip=True)
            
            # The odds are in the button
            btn = sel.select_one('bcdk-bet-button-odds-animated')
            odd_str = btn.get_text(strip=True).replace(',', '.') if btn else "1.85"
            try:
                odd_val = float(odd_str)
            except ValueError:
                odd_val = 1.85
                
            # Parse 'Jadarian Price + de 8,5' vs '- de 8,5'
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
                # TD Scorers
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
        print("Warning: Scraped data is empty. Anti-bot triggered or format changed.")
        
    return df

async def main():
    if not os.path.exists("data/links.txt"):
        print("Error: data/links.txt not found. Please create it with Betclic URLs.")
        return

    with open("data/links.txt", "r") as f:
        links = [line.strip() for line in f if line.strip()]

    if not links:
        print("No links found in data/links.txt")
        return

    print(f"Found {len(links)} links. Starting sequential scraping...")
    
    all_dfs = []
    
    for i, url in enumerate(links):
        df = await scrape_match(url)
        
        if df is None:
            print("Aborting remaining links due to anti-bot block.")
            break
            
        if not df.is_empty():
            all_dfs.append(df)
            
        if i < len(links) - 1:
            # Slow Scrape Mode: Wait 45 to 90 seconds to avoid DataDome velocity triggers
            import random
            wait_time = random.uniform(45.0, 90.0)
            print(f"🐢 Slow Scrape: Waiting {wait_time:.1f} seconds to simulate human reading time and protect IP...")
            await asyncio.sleep(wait_time)
            
    if all_dfs:
        final_df = pl.concat(all_dfs)
        os.makedirs("data", exist_ok=True)
        final_df.write_parquet("data/betclic_parsed_odds.parquet")
        print(f"Successfully saved a total of {len(final_df)} props to data/betclic_parsed_odds.parquet")
    else:
        print("No data extracted from any links.")

if __name__ == "__main__":
    asyncio.run(main())
