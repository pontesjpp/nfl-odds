import re
from bs4 import BeautifulSoup
import json

with open('joueurs_tab.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f, 'html.parser')

market_boxes = soup.find_all('div', class_=lambda c: c and 'marketBox' in c and 'marketBox_container' not in c and 'marketBox_head' not in c and 'marketBox_body' not in c and 'marketBox_lineSelection' not in c and 'marketBox_spacer' not in c)
# Actually it's easier to just find all divs with exactly class 'marketBox' or 'marketBox is-something'

markets = soup.select('.marketBox')
print(f"Found {len(markets)} markets")

for i, m in enumerate(markets[:5]):
    head = m.select_one('.marketBox_head')
    market_name = head.get_text(strip=True) if head else "Unknown Market"
    print(f"\nMarket: {market_name}")
    
    selections = m.select('.marketBox_lineSelection')
    for sel in selections[:4]:
        label = sel.select_one('.marketBox_label')
        label_text = label.get_text(strip=True) if label else ""
        
        # In some markets like over/under, the line is in the label ("+ de 8,5")
        # Let's also look for odds
        btn = sel.select_one('bcdk-bet-button-odds-animated')
        odd_val = btn.get_text(strip=True) if btn else ""
        
        print(f"  Selection: {label_text} | Odds: {odd_val}")
