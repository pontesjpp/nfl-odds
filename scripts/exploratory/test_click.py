import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        await page.goto("https://www.betclic.fr/football-americain-samerican_football/nfl-c84/seattle-seahawks-new-england-patriots-m1114571215626242", wait_until="domcontentloaded")
        
        await page.wait_for_timeout(2000)
        
        # Nuke everything that could be over the page
        await page.evaluate("""
            document.querySelectorAll('div[class*="overlay"], div[class*="backdrop"], [id*="privacy"]').forEach(el => el.remove());
            document.body.style.overflow = 'auto';
        """)
        
        tab = page.locator('div[data-qa="tab-btn"]', has_text="Joueurs").first
        
        # Scroll it into view and click natively
        await tab.scroll_into_view_if_needed()
        await tab.click()
        print("Clicked organically!")
        
        for i in range(5):
            await page.wait_for_timeout(1000)
            count = await page.locator('.marketBox').count()
            print(f"Second {i}: {count} markets")
            if count > 9: break
            
        await browser.close()
asyncio.run(run())
