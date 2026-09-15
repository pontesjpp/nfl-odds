import asyncio
import os
import argparse
from nfl_odds.odds.betclic_scraper import run_betclic_scraping

def main():
    parser = argparse.ArgumentParser(description="NFL Odds Scraper - Betclic")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Executa em modo rápido (delay de 5-12s entre jogos). Cuidado com rate limits."
    )
    parser.add_argument(
        "--slow",
        action="store_true",
        default=False,
        help="Força modo slow scraper (delay de 30-60s entre jogos). Padrão se --fast não for passado."
    )
    parser.add_argument(
        "--links",
        default="data/links.txt",
        help="Caminho do arquivo com as URLs da Betclic (padrão: data/links.txt)"
    )
    args = parser.parse_args()

    # O padrão é slow_mode a menos que o usuário passe explicitamente --fast
    slow_mode = not args.fast

    asyncio.run(run_betclic_scraping(slow_mode=slow_mode, links_file=args.links))

if __name__ == "__main__":
    main()
