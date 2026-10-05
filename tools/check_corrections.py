"""Check docs/data/corrections.json against docs/data/places.json.

Every edit's `find` must occur exactly once in its page text at the moment it is applied
(edits for the same page apply in file order, as the site does). Exit code 1 on any problem.

    python tools/check_corrections.py [docs]
"""
import json, sys

root = sys.argv[1] if len(sys.argv) > 1 else 'docs'
places = {p['id']: p for p in json.load(open(f'{root}/data/places.json', encoding='utf-8'))['places']}
edits = json.load(open(f'{root}/data/corrections.json', encoding='utf-8'))['edits']

texts, bad = {}, 0
for n, ed in enumerate(edits):
    p = places.get(ed['id'])
    pages = (p or {}).get('description') or []
    if ed['page'] >= len(pages):
        print(f'#{n} {ed["id"]}: no page {ed["page"]}')
        bad += 1
        continue
    key = (ed['id'], ed['page'])
    t = texts.setdefault(key, pages[ed['page']]['text'])
    c = t.count(ed['find'])
    if c != 1:
        print(f'#{n} {ed["id"]}/{ed["page"]}: find occurs {c} times: {ed["find"][:40]!r}')
        bad += 1
        continue
    texts[key] = t.replace(ed['find'], ed['replace'])

print(f'{len(edits)} edits, {len(texts)} pages, {bad} problems')
sys.exit(1 if bad else 0)
