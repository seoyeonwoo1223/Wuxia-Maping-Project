"""Check docs/data/corrections.json against docs/data/places.json.

Every edit's `find` must occur exactly once in its page text at the moment it is applied
(edits for the same field apply in file order, as the site does).
`emperors` entries fix the 제왕연표 rows by original row index.
`field` defaults to the page text; 'title' fixes the page title, 'name'/'hanja' the place itself. Exit code 1 on any problem.

    python tools/check_corrections.py [docs]
"""
import json, sys

root = sys.argv[1] if len(sys.argv) > 1 else 'docs'
places = {p['id']: p for p in json.load(open(f'{root}/data/places.json', encoding='utf-8'))['places']}
edits = json.load(open(f'{root}/data/corrections.json', encoding='utf-8'))['edits']
# landmark articles (lm28…) carry text/title on the article itself
articles = {a['id']: a for a in json.load(open(f'{root}/data/landmarks.json', encoding='utf-8'))}

texts, bad = {}, 0
for n, ed in enumerate(edits):
    p = places.get(ed['id'])
    field = ed.get('field', 'text')          # 'text' | 'title' (page fields) or 'name' | 'hanja' (place fields)
    if ed['id'] in articles:
        key, t = (ed['id'], field), articles[ed['id']][field]
        t = texts.setdefault(key, t)
        if t.count(ed['find']) != 1:
            print(f'#{n} {ed["id"]}/{field}: find occurs {t.count(ed["find"])} times: {ed["find"][:40]!r}')
            bad += 1
        else:
            texts[key] = t.replace(ed['find'], ed['replace'])
        continue
    if p is None:
        print(f'#{n} {ed["id"]}: no such place')
        bad += 1
        continue
    if field in ('name', 'hanja'):
        key, t = (ed['id'], field), p[field]
    else:
        pages = p.get('description') or []
        if ed.get('page', 0) >= len(pages):
            print(f'#{n} {ed["id"]}: no page {ed.get("page")}')
            bad += 1
            continue
        key, t = (ed['id'], ed['page'], field), pages[ed['page']][field]
    t = texts.setdefault(key, t)
    c = t.count(ed['find'])
    if c != 1:
        print(f'#{n} {ed["id"]}/{field}: find occurs {c} times: {ed["find"][:40]!r}')
        bad += 1
        continue
    texts[key] = t.replace(ed['find'], ed['replace'])

# emperor table fixes: `row` indexes the original dynasty table and `expect` must be that row's name
dyns = {d['id']: d for d in json.load(open(f'{root}/data/emperors.json', encoding='utf-8'))}
emp_edits = json.load(open(f'{root}/data/corrections.json', encoding='utf-8')).get('emperors', [])
for n, ed in enumerate(emp_edits):
    d = dyns.get(ed['dyn'])
    if d is None:
        print(f'emperors #{n}: no such dynasty {ed["dyn"]}')
        bad += 1
    elif 'append' not in ed and (ed['row'] >= len(d['rows']) or d['rows'][ed['row']]['name'] != ed['expect']):
        print(f'emperors #{n} {ed["dyn"]}: row {ed["row"]} is not {ed["expect"]!r}')
        bad += 1

print(f'{len(edits)} edits, {len(texts)} pages, {len(emp_edits)} emperor fixes, {bad} problems')
sys.exit(1 if bad else 0)
