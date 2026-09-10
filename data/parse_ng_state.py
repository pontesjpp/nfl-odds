import json
import re

with open('betclic_page.html', 'r', encoding='utf-8') as f:
    html = f.read()

match = re.search(r'<script id="ng-state" type="application/json">(.*?)</script>', html)
if match:
    data = json.loads(match.group(1))
    with open('ng_state.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print("Saved ng_state.json")
else:
    print("Not found")
