import asyncio
from playwright.async_api import async_playwright
import polars as pl
from datetime import datetime

class BetclicScraper:
    def __init__(self):
        self.base_url = "https://www.betclic.fr/american_football-samerican_football/nfl-c84"
        
    async def scrape_nfl_props(self) -> pl.DataFrame:
        """
        Scrape NFL Player Props from Betclic.
        This uses Playwright to intercept the internal API calls for odds to avoid fragile DOM parsing.
        """
        scraped_odds = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # Setup a response interceptor to catch the JSON data Betclic fetches
            # They usually fetch data from something like:
            # https://offer.betclic.fr/api/pub/v2/competitions/14?application=2&countrycode=fr...
            
            async def handle_response(response):
                # Check if it's the right endpoint returning JSON
                if "api/pub/v2/competitions/14" in response.url and response.status == 200:
                    try:
                        data = await response.json()
                        self._parse_betclic_json(data, scraped_odds)
                    except Exception as e:
                        print("Could not parse JSON payload:", e)
                        
            page.on("response", handle_response)
            
            print(f"[{datetime.now()}] Navegando para a página NFL da Betclic...")
            try:
                await page.goto(self.base_url, wait_until="networkidle", timeout=30000)
            except Exception as e:
                print(f"Timeout ou erro de navegação: {e}")
                
            # Allow time for background API calls to complete and interceptor to catch them
            await page.wait_for_timeout(5000)
            await browser.close()
            
        if not scraped_odds:
            print("Nenhuma odd interceptada. Pode ser que não haja jogos abertos ou a API mudou.")
            return pl.DataFrame()
            
        # ---------------------------------------------------------
        # NEW: Save to Database
        # ---------------------------------------------------------
        from nfl_odds.data.database import SessionLocal, OddsSnapshot
        
        session = SessionLocal()
        try:
            db_snapshots = []
            for item in scraped_odds:
                snapshot = OddsSnapshot(
                    timestamp=item["timestamp"],
                    bookmaker=item["bookmaker"],
                    market=item["raw_market"],      # Raw market name for now
                    player_name=item["raw_selection"], # We will parse this to clean player name later
                    line=item.get("line", 0.0),        # Extracted line
                    side="over",                       # Need dynamic extraction
                    odds=item["odds"],
                    game_id=item["raw_match"]
                )
                db_snapshots.append(snapshot)
                
            session.add_all(db_snapshots)
            session.commit()
            print(f"[{datetime.now()}] Salvos {len(db_snapshots)} snapshots no Banco de Dados!")
        except Exception as e:
            session.rollback()
            print(f"Erro ao salvar no banco de dados: {e}")
        finally:
            session.close()
            
        return pl.DataFrame(scraped_odds)

    def _parse_betclic_json(self, data: dict, results_list: list):
        """
        Extract player props from Betclic's internal JSON structure.
        """
        try:
            matches = data.get("unifiedEvents", [])
            for match in matches:
                match_name = match.get("name", "Unknown Match")
                markets = match.get("markets", [])
                
                for market in markets:
                    market_name = market.get("name", "")
                    if "courses" in market_name.lower() or "yards" in market_name.lower() or "passes" in market_name.lower():
                        selections = market.get("selections", [])
                        
                        for sel in selections:
                            player_and_line = sel.get("name", "")
                            odds = sel.get("odds", 0)
                            
                            # Basic line extraction attempt
                            import re
                            line_match = re.search(r"(\d+\.\d+)", player_and_line)
                            line_val = float(line_match.group(1)) if line_match else 0.0
                            
                            results_list.append({
                                "timestamp": datetime.now(),
                                "bookmaker": "Betclic",
                                "raw_match": match_name,
                                "raw_market": market_name,
                                "raw_selection": player_and_line,
                                "line": line_val,
                                "odds": odds
                            })
        except Exception as e:
            print(f"Erro no parse do JSON: {e}")

if __name__ == "__main__":
    scraper = BetclicScraper()
    df_scraped = asyncio.run(scraper.scrape_nfl_props())
    print("Scraping workflow testado e integrado ao BD.")
