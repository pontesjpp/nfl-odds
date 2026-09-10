import nflreadpy as nfl
import requests
import os
import polars as pl

def download_logos():
    print("Loading teams...")
    teams = nfl.load_teams()
    
    if isinstance(teams, pl.DataFrame):
        teams = teams.to_pandas()
        
    os.makedirs("frontend/public/logos", exist_ok=True)
    
    for idx, row in teams.iterrows():
        abbr = row['team_abbr']
        url = row['team_logo_espn']
        if not url or str(url).lower() == 'nan':
            continue
            
        filepath = f"frontend/public/logos/{abbr}.png"
        
        print(f"Downloading {abbr}...")
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                with open(filepath, 'wb') as f:
                    f.write(res.content)
            else:
                print(f"Failed {abbr}: {res.status_code}")
        except Exception as e:
            print(f"Error {abbr}: {e}")

if __name__ == "__main__":
    download_logos()
