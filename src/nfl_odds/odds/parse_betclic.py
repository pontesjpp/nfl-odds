import re
import json
import polars as pl
import os

def parse_odds(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
        
    data = []
    current_category = None
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check for categories
        if line in ["Nombre de Yards à la réception", "Nombre de Yards à la passe", "Nombre de Yards à la course",
                    "Nombre de Yards à la passe (paliers)", "Nombre de Yards à la réception (paliers)", "Nombre de Yards à la course (paliers)",
                    "Duos & Trios", "Marqueur de TD & Vainqueur", "Premier/dernier marqueur"]:
            current_category = line
            i += 1
            continue
            
        # Ignore sub-categories for now, just keep track of the main categories
        if "Le duo marque" in line or "Le trio marque" in line or "Marqueur de touchdown" in line or "Premier marqueur" in line or "Dernier marqueur" in line or "Double chance" in line:
            current_category = line
            i += 1
            continue
            
        if current_category in ["Nombre de Yards à la réception", "Nombre de Yards à la passe", "Nombre de Yards à la course"]:
            # Format: "Player Name + de 8,5" or "Player Name - de 8,5"
            match = re.match(r'(.+) ([+-]) de ([\d,]+)', line)
            if match:
                player = match.group(1).strip()
                side_str = match.group(2)
                side = "over" if side_str == "+" else "under"
                line_val = float(match.group(3).replace(',', '.'))
                
                market = ""
                if "réception" in current_category: market = "receiving_yards"
                elif "passe" in current_category: market = "passing_yards"
                elif "course" in current_category: market = "rushing_yards"
                
                data.append({
                    "player_name": player,
                    "market": market,
                    "side": side,
                    "line": line_val,
                    "odds": 1.85, # Default odds since they aren't in the copy-paste
                    "bookmaker": "Betclic"
                })
        i += 1
        
    return pl.DataFrame(data)

if __name__ == "__main__":
    df = parse_odds("data/raw_odds.txt")
    print(df)
    df.write_parquet("data/betclic_parsed_odds.parquet")
