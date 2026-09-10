import re
import json

def parse_odds(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
        
    data = []
    current_category = None
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check for categories
        if line in ["Nombre de Yards à la réception", "Nombre de Yards à la passe", "Nombre de Yards à la course"]:
            current_category = line
            i += 1
            continue
        elif "paliers" in line or "Duos & Trios" in line or "Marqueur de TD" in line or "Premier/dernier" in line or "Double chance" in line:
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
                    "category": current_category,
                    "market": market,
                    "player": player,
                    "side": side,
                    "line": line_val
                })
        i += 1
        
    return data

if __name__ == "__main__":
    odds = parse_odds("data/raw_odds.txt")
    print(json.dumps(odds[:5], indent=2))
    print(f"Total parsed: {len(odds)}")
