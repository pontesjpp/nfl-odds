import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        # Apply stealth!
        await Stealth().apply_stealth_async(page)
        
        url = "https://www.betclic.fr/football-americain-samerican_football/nfl-c84/seattle-seahawks-new-england-patriots-m1114571215626242"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        
        await page.evaluate("""
            document.querySelectorAll('div[class*="overlay"], div[class*="backdrop"], [id*="privacy"]').forEach(el => el.remove());
        """)
        
        try:
            tab = page.get_by_text("Joueurs", exact=True)
            await tab.scroll_into_view_if_needed(timeout=5000)
            await tab.click(timeout=5000)
            
            for i in range(5):
                await page.wait_for_timeout(1000)
                count = await page.locator('.marketBox').count()
                print(f"Second {i}: {count} markets")
                if count > 15: break
        except Exception as e:
            print("Failed:", e)
            
        await browser.close()

asyncio.run(run())
