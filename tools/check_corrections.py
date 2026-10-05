"""Check docs/data/corrections.json against docs/data/places.json.

Every edit's `find` must occur exactly once in its page text at the moment it is applied
(edits for the same field apply in file order, as the site does).
`field` defaults to the page text; 'title' fixes the page title, 'name'/'hanja' the place itself. Exit code 1 on any problem.

    python tools/check_corrections.py [docs]
"""
import json, sys

root = sys.argv[1] if len(sys.argv) > 1 else 'docs'
places = {p['id']: p for p in json.load(open(f'{root}/data/places.json', encoding='utf-8'))['places']}
edits = json.load(open(f'{root}/data/corrections.json', encoding='utf-8'))['edits']

texts, bad = {}, 0
for n, ed in enumerate(edits):
    p = places.get(ed['id'])
    field = ed.get('field', 'text')          # 'text' | 'title' (page fields) or 'name' | 'hanja' (place fields)
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

print(f'{len(edits)} edits, {len(texts)} pages, {bad} problems')
sys.exit(1 if bad else 0)
