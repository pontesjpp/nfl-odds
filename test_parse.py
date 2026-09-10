import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup
import re

async def scrape_match(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await Stealth().apply_stealth_async(page)
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.evaluate("""
            document.querySelectorAll('div[class*="overlay"], div[class*="backdrop"], [id*="privacy"]').forEach(el => el.remove());
        """)
        tab = page.get_by_text("Joueurs", exact=True)
        await tab.scroll_into_view_if_needed(timeout=5000)
        await tab.click(timeout=5000)
        await page.wait_for_timeout(3000)
        html = await page.content()
        await browser.close()
        
    soup = BeautifulSoup(html, 'html.parser')
    markets = soup.select('.marketBox')
    
    for m in markets:
        head = m.select_one('.marketBox_head')
        if not head: continue
        market_name = head.get_text(strip=True)
        if "Yards" in market_name:
            selections = m.select('.marketBox_lineSelection')
            for sel in selections:
                label = sel.select_one('.marketBox_label')
                if label:
                    label_text = label.get_text(strip=True)
                    match = re.match(r'(.+) ([+-]) de ([\d,]+)', label_text)
                    print(f"[{market_name}] Label: '{label_text}' | Matched: {bool(match)}")

if __name__ == "__main__":
    url = "https://www.betclic.fr/football-americain-samerican_football/nfl-c84/seattle-seahawks-new-england-patriots-m1114571215626242"
    asyncio.run(scrape_match(url))
