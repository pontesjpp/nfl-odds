import asyncio
from playwright.async_api import async_playwright
import time

async def scrape(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()
        
        print(f"Navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
            
        print("Looking for Joueurs tab...")
        try:
            tab = page.locator('span.tab_label', has_text='Joueurs').first
            await tab.click(force=True)
            print("Clicked tab with FORCE!")
            
            # Wait until there are more than 15 market boxes (since main page has 9)
            print("Waiting for markets to load...")
            for _ in range(20):
                count = await page.locator('.marketBox').count()
                if count > 15:
                    print(f"Loaded {count} markets!")
                    break
                await page.wait_for_timeout(500)
                
            await page.wait_for_timeout(1000)
            
            # Now dump the innerHTML
            html = await page.content()
            with open("joueurs_tab.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("Saved joueurs_tab.html")
        except Exception as e:
            print(f"Failed: {e}")
            
        await browser.close()

asyncio.run(scrape("https://www.betclic.fr/football-americain-samerican_football/nfl-c84/seattle-seahawks-new-england-patriots-m1114571215626242"))
