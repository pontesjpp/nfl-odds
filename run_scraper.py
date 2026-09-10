import asyncio
import os
import polars as pl
from nfl_odds.odds.betclic_scraper import scrape_match

async def main():
    links_file = "data/links.txt"
    if not os.path.exists(links_file):
        print(f"File {links_file} not found. Please create it with one URL per line.")
        return
        
    with open(links_file, "r") as f:
        links = [line.strip() for line in f if line.strip()]
        
    # Deduplicate links just in case
    links = list(set(links))
    
    print(f"Encontrados {len(links)} jogos únicos para raspar.")
    
    all_dfs = []
    for i, link in enumerate(links, 1):
        print(f"--- Processando jogo {i}/{len(links)} ---")
        try:
            df = await scrape_match(link)
            if df is not None and len(df) > 0:
                all_dfs.append(df)
            else:
                print("Nenhum dado retornado para este jogo.")
        except Exception as e:
            print(f"Erro ao processar o jogo: {e}")
            
        # Adiciona um delay aleatório entre 5 e 12 segundos para não acionar o anti-bot
        if i < len(links):
            import random
            delay = random.uniform(5.0, 12.0)
            print(f"Esperando {delay:.1f} segundos para evitar bloqueio de IP...")
            await asyncio.sleep(delay)
            
            
    if all_dfs:
        df_final = pl.concat(all_dfs)
        out_path = "data/betclic_parsed_odds.parquet"
        df_final.write_parquet(out_path)
        print(f"\n✅ Scraping concluído! Foram salvas {len(df_final)} props totais em '{out_path}'.")
        print("Agora você pode rodar: uv run python pipeline.py --live")
    else:
        print("\n❌ Nenhuma prop foi encontrada/raspada em nenhum jogo.")

if __name__ == "__main__":
    asyncio.run(main())
