import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup
import polars as pl
import re

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await Stealth().apply_stealth_async(page)
        await page.goto("https://www.betclic.fr/football-americain-samerican_football/nfl-c84/seattle-seahawks-new-england-patriots-m1114571215626242", wait_until="domcontentloaded")
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
    print("TOTAL MARKETS:", len(markets))
    data = []
    for m in markets:
        head = m.select_one('.marketBox_head')
        if not head: continue
        market_name = head.get_text(strip=True)
        if "Yards" not in market_name and "Touchdown" not in market_name: continue
        selections = m.select('.marketBox_lineSelection')
        for sel in selections:
            label = sel.select_one('.marketBox_label')
            if not label: continue
            label_text = label.get_text(strip=True)
            match = re.match(r'(.+) ([+-]) de ([\d,]+)', label_text)
            if match:
                data.append({"player": match.group(1), "market": market_name})

    print("DATA LENGTH:", len(data))
    if len(data) > 0:
        print(pl.DataFrame(data).head(5))

asyncio.run(run())
