import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        await page.goto("https://www.betclic.fr/football-americain-samerican_football/nfl-c84/seattle-seahawks-new-england-patriots-m1114571215626242", wait_until="domcontentloaded")
        
        await page.evaluate("""
            document.querySelectorAll('.cdk-overlay-container, .tc-privacy-wrapper, [id^="tc-privacy"]').forEach(el => el.remove());
            document.body.style.overflow = 'auto';
        """)
        
        # Click the actual parent element or dispatch event
        await page.evaluate("""
            const tabs = Array.from(document.querySelectorAll('span.tab_label'));
            const joueurs = tabs.find(t => t.textContent.includes('Joueurs'));
            if (joueurs) {
                // Find nearest clickable parent
                let parent = joueurs.parentElement;
                while(parent && parent.tagName !== 'A' && parent.tagName !== 'DIV') {
                    if (parent.classList.contains('tab_link')) break;
                    parent = parent.parentElement;
                }
                parent.click();
            }
        """)
        print("Clicked via JS!")
        
        for i in range(10):
            await page.wait_for_timeout(1000)
            count = await page.locator('.marketBox').count()
            print(f"Second {i}: {count} markets")
            if count > 9: break
        
        await browser.close()
asyncio.run(run())
