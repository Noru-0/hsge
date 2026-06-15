"""Quick analysis of cleaned frontier."""
import json
from collections import defaultdict
from urllib.parse import urlparse

P = {'customer','checkout','sales','catalogsearch','catalog','search',
     'contact','privacy','newsletter','review','wishlist','vault','downloadable'}

with open('outputs/wa_run/frontier_clean.jsonl', encoding='utf-8') as f:
    rec = json.loads(f.readline())
    frontier = rec['frontier']

groups = defaultdict(list)
for item in frontier:
    u = item['url']
    p = urlparse(u).path.strip('/')
    s = [x for x in p.split('/') if x]
    if not s:
        groups['ROOT'].append(u)
        continue
    if s[0] in P:
        key = 'FUNC:' + '/'.join(s[:min(3, len(s))])
        groups[key].append(u)
        continue
    # product heuristic
    if len(s) == 1 and s[0].endswith('.html'):
        name = s[0].replace('.html', '')
        if len(name) > 35 and name.count('-') > 2:
            groups['PROD'].append(u)
            continue
    groups['CAT:' + s[0]].append(u)

print("=== Clean Frontier Breakdown (node 1) ===")
func_total = 0
cat_total = 0
for k, v in sorted(groups.items(), key=lambda x: -len(x[1])):
    tag = ''
    if k.startswith('FUNC:'):
        func_total += len(v)
        tag = '[FUNC]'
    elif k == 'PROD':
        tag = '[PROD]'
    else:
        cat_total += len(v)
        tag = '[CAT]'
    print(f'  [{len(v):2d}] {tag} {k}')
    if len(v) <= 5:
        for uu in v:
            print(f'       {uu}')

print(f'\nTOTAL: {len(frontier)} URLs')
print(f'  Functional: {func_total}')
print(f'  Categories: {cat_total}')
print(f'  Products:   {len(groups.get("PROD", []))}')
