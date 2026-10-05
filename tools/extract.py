"""Extract map SVGs and structured data from legacy/murim.swf into docs/.

    python tools/extract.py [legacy/murim.swf] [docs]

Outputs
  docs/maps/china.svg, docs/maps/<province>.svg
  docs/data/places.json     provinces, cities, sights, sects (+ descriptions, map coordinates in SVG px)
  docs/data/emperors.json   帝王年表
  docs/data/landmarks.json  主要地名 articles
  docs/data/about.json      credits / notices from the original
  docs/data/report.json     linking statistics and leftover texts
"""
import json, os, re, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from swflib import SWF, IDENTITY, mat_mul, mat_apply, char_bounds, button_gotos  # noqa: E402
from swfsvg import Renderer, path_bounds  # noqa: E402

PROVINCE_IDS = {
    '감숙': 'gansu', '강서': 'jiangxi', '강소': 'jiangsu', '광동': 'guangdong', '광서': 'guangxi',
    '귀주': 'guizhou', '길림': 'jilin', '내몽고': 'neimenggu', '녕하': 'ningxia', '복건': 'fujian',
    '북경': 'beijing', '사천': 'sichuan', '산동': 'shandong', '산서': 'shanxi', '상해': 'shanghai',
    '서장': 'xizang', '섬서': 'shaanxi', '신강': 'xinjiang', '안휘': 'anhui', '요녕': 'liaoning',
    '운남': 'yunnan', '절강': 'zhejiang', '중경': 'chongqing', '천진': 'tianjin', '청해': 'qinghai',
    '하남': 'henan', '하북': 'hebei', '호남': 'hunan', '호북': 'hubei', '흑룡강': 'heilongjiang',
    '해남': 'hainan',
}
TITLE_PREFIX = '武林用中國全圖'
SIGHT_SUFFIX = tuple('山嶺峰湖關宮林窟寺')
CITY_MARKER_MAX = 900   # twips between a label box and its marker dot

used_texts = set()      # text character ids that ended up in some output


def T(s):
    """Normalise Flash text: CR line breaks, trailing blanks."""
    lines = [l.rstrip() for l in s.replace('\r\n', '\r').replace('\n', '\r').split('\r')]
    return '\n'.join(lines).strip('\n')


def split_name(s):
    """'아미산(峨嵋山)' -> ('아미산', '峨嵋山'); handles [] too and stray spaces."""
    s = s.strip()
    m = re.match(r'^(.*?)\s*[(\[]([^)\]]*)[)\]]\s*(.*)$', s)
    if not m:
        return re.sub(r'\s+', '', s), ''
    ko = re.sub(r'\s+', '', m.group(1) + m.group(3))
    hanja = m.group(2).strip()
    if re.fullmatch(r'[\u3400-\u9fff?\s]+', hanja):
        hanja = re.sub(r'\s+', '', hanja)
    return ko, hanja


def text_of(swf, cid):
    used_texts.add(cid)
    return swf.chars[cid][1]['text']


def is_text(swf, cid):
    return swf.chars.get(cid, (None,))[0] == 'text'


def button_texts(swf, bid):
    seen, out = set(), []
    for r in swf.chars[bid][1]['records']:
        if is_text(swf, r['id']) and r['id'] not in seen:
            seen.add(r['id'])
            out.append(r['id'])
    return out


def px(v):
    return round(v / 20, 1)


def center(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def box_dist(b, x, y):
    dx = max(b[0] - x, 0, x - b[2])
    dy = max(b[1] - y, 0, y - b[3])
    return (dx * dx + dy * dy) ** 0.5


def write_svg(path, swf, display, skip, path_filter=None):
    r = Renderer(swf, skip=skip, path_filter=path_filter)
    body = r.display(display, IDENTITY, None)
    pad = 100
    x0, y0, x1, y1 = r.bounds
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    vb = (x0 / 20, y0 / 20, (x1 - x0) / 20, (y1 - y0) / 20)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(r.document(f'<g transform="scale(0.05)">{body}</g>', vb))
    return [round(v, 1) for v in vb]


# ---------------------------------------------------------------- national map

def national(swf, out):
    f0 = swf.root.frames[0]['display']
    label_to_frame = {f['label']: i for i, f in enumerate(swf.root.frames) if f['label']}
    frame_to_label = {i: l for l, i in label_to_frame.items()}
    provinces = {}
    for d, p in f0.items():
        if swf.chars[p['id']][0] != 'button':
            continue
        tg = [t for k, t in button_gotos(swf, p['id']) if k == 'frame']
        if tg and frame_to_label.get(tg[0]) in PROVINCE_IDS:
            name = frame_to_label[tg[0]]
            b = char_bounds(swf, p['id'], p['matrix'])
            # the province name is drawn as white glyph outlines inside the region shape
            glyphs = [path_bounds(mat_mul(p['matrix'], r['matrix']), path)
                      for r in swf.chars[p['id']][1]['records'] if r['states'] & 1
                      and swf.chars[r['id']][0] == 'shape'
                      for path in swf.chars[r['id']][1]['paths']
                      if path.get('fill', {}).get('color', [])[:3] == [255, 255, 255]]
            if glyphs:
                b = (min(g[0] for g in glyphs), min(g[1] for g in glyphs),
                     max(g[2] for g in glyphs), max(g[3] for g in glyphs))
            provinces[name] = {'depth': d, 'frame': tg[0], 'bounds': b}
    # map = everything up to the province buttons, minus the title (depth 2) and the UI frame overlay
    ui_frame = max(d for d, p in f0.items() if d < 100 and swf.chars[p['id']][0] == 'shape')
    map_display = {d: p for d, p in f0.items() if d < 100 and d not in (2, ui_frame)}
    by_depth = {v['depth']: PROVINCE_IDS[k] for k, v in provinces.items()}

    r = Renderer(swf)
    parts = []
    for d in sorted(map_display):
        p = map_display[d]
        svg = r.char(p['id'], p.get('matrix', IDENTITY), p.get('cxform'))
        if d in by_depth:
            svg = f'<g class="province" data-id="{by_depth[d]}">{svg}</g>'
        parts.append(svg)
    x0, y0, x1, y1 = r.bounds
    x0, y0, x1, y1 = x0 - 100, y0 - 100, x1 + 100, y1 + 100
    vb = (x0 / 20, y0 / 20, (x1 - x0) / 20, (y1 - y0) / 20)
    with open(f'{out}/maps/china.svg', 'w', encoding='utf-8') as fh:
        fh.write(r.document(f'<g transform="scale(0.05)">{"".join(parts)}</g>', vb))
    return provinces, [round(v, 1) for v in vb]


# ---------------------------------------------------------------- province maps

def province(swf, name, root_frame, out, report):
    pid = PROVINCE_IDS[name]
    fr = swf.root.frames[root_frame]['display']
    sprite = fr[3]['id']
    tl = swf.chars[sprite][1]

    def title_texts(display):
        return [p for p in display.values() if is_text(swf, p['id'])
                and swf.chars[p['id']][1]['text'].startswith(TITLE_PREFIX)]

    def popup(fi):
        """(title, body) text ids of the description window shown in sprite frame fi."""
        disp = tl.frames[fi]['display']
        titles = title_texts(disp)
        if not titles:
            return None
        tdepth = min(d for d, p in disp.items() if p in titles)
        bodies = sorted((d, p) for d, p in disp.items() if d > tdepth and is_text(swf, p['id']))
        return titles[0]['id'], [p['id'] for d, p in bodies]

    closed = next(i for i, f in enumerate(tl.frames) if not title_texts(f['display']))
    base = tl.frames[closed]['display']

    # Province description (frame 0) tells us whether this sprite really belongs to this province.
    t0, b0 = popup(0)
    head = swf.chars[t0][1]['text'][len(TITLE_PREFIX):].strip(' -')
    head_ko, head_hanja = split_name(head.split('-')[0])
    if not head_ko.startswith(name):
        report['placeholder_provinces'].append({'province': pid, 'name': name, 'copied_from': head_ko})
        return None

    # list panel ("각대문파"): the header bar path under the heading text and the box below it
    panel = None
    shape_paths = [(p.get('matrix', IDENTITY), path) for d, p in base.items() if swf.chars[p['id']][0] == 'shape'
                   for path in swf.chars[p['id']][1]['paths']]
    for d, p in base.items():
        if is_text(swf, p['id']) and T(swf.chars[p['id']][1]['text']) == '각대문파':
            used_texts.add(p['id'])
            cx, cy = center(char_bounds(swf, p['id'], p['matrix']))
            heads = [pb for pb in (path_bounds(m, path) for m, path in shape_paths)
                     if pb[0] <= cx <= pb[2] and pb[1] <= cy <= pb[3] and pb[2] - pb[0] < 5000]
            if not heads:
                continue
            hd = min(heads, key=lambda pb: (pb[2] - pb[0]) * (pb[3] - pb[1]))
            parts = [pb for pb in (path_bounds(m, path) for m, path in shape_paths)
                     if abs(pb[0] - hd[0]) < 300 and abs(pb[2] - hd[2]) < 300
                     and pb[1] <= hd[3] + 100 and pb[3] >= hd[1]] + [hd]
            panel = (min(q[0] for q in parts), min(q[1] for q in parts),
                     max(q[2] for q in parts), max(q[3] for q in parts))

    def in_panel(b):
        if panel is None or b is None:
            return False
        cx, cy = center(b)
        return panel[0] <= cx <= panel[2] and panel[1] <= cy <= panel[3]

    def skip(cid, place):
        kind = swf.chars[cid][0]
        if kind == 'text':
            return True
        return kind == 'button' and in_panel(char_bounds(swf, cid, place.get('matrix', IDENTITY)))

    vb = write_svg(f'{out}/maps/{pid}.svg', swf, base, skip, lambda m, path: not in_panel(path_bounds(m, path)))

    # --- labels and markers on the map
    markers = []
    for d, p in base.items():
        if swf.chars[p['id']][0] == 'sprite' and swf.chars[p['id']][1].frames:
            b = char_bounds(swf, p['id'], p['matrix'])
            if b and (b[2] - b[0]) < 400:
                markers.append(center(b))
    labels = []
    for d, p in sorted(base.items()):
        if not is_text(swf, p['id']):
            continue
        raw = T(swf.chars[p['id']][1]['text'])
        if not raw or raw.count('\n') > 1 or len(raw) > 30 or raw in ('각대문파', '각대세가'):
            continue
        raw = raw.replace('\n', '') if raw.count('(') == 1 else raw.replace('\n', ' ')
        b = char_bounds(swf, p['id'], p['matrix'])
        if in_panel(b):
            continue
        labels.append({'cid': p['id'], 'raw': raw, 'box': b, 'depth': d})

    # greedy label <-> marker assignment
    pairs = sorted((box_dist(l['box'], mx, my), li, mi)
                   for li, l in enumerate(labels) for mi, (mx, my) in enumerate(markers))
    lab_m, mk_l = {}, {}
    for dist, li, mi in pairs:
        if dist > CITY_MARKER_MAX:
            break
        if li in lab_m or mi in mk_l:
            continue
        lab_m[li], mk_l[mi] = mi, li

    entries = []
    for li, l in enumerate(labels):
        ko, hanja = split_name(l['raw'])
        used_texts.add(l['cid'])
        pt = markers[lab_m[li]] if li in lab_m else center(l['box'])
        if re.search(r'(성|자치구|시)$', ko) and re.search(r'(省|自治區|市)$', hanja) and li not in lab_m:
            neighbor = next((v for k, v in PROVINCE_IDS.items() if ko.startswith(k)), None)
            entries.append({'id': f'{pid}-n{l["depth"]}', 'name': ko, 'hanja': hanja, 'province': pid,
                            'kind': '인접 지역', 'link': neighbor, 'map': pid, 'x': px(pt[0]), 'y': px(pt[1]),
                            'label': {'x': px(l['box'][0]), 'y': px(l['box'][1])}, 'located': 'label'})
            continue
        kind = '도시' if li in lab_m else ('명승지' if hanja.endswith(SIGHT_SUFFIX) else '지명')
        entries.append({'id': f'{pid}-l{l["depth"]}', 'name': ko, 'hanja': hanja, 'province': pid,
                        'kind': kind, 'map': pid, 'x': px(pt[0]), 'y': px(pt[1]),
                        'label': {'x': px(l['box'][0]), 'y': px(l['box'][1])}, 'located': 'label'})

    # --- hotspot buttons -> description frames (and pages linked from inside the popups)
    def popup_links(fi):
        disp = tl.frames[fi]['display']
        out_ = []
        for d, p in sorted(disp.items()):
            if swf.chars[p['id']][0] == 'button' and base.get(d) != p:
                for k, t in button_gotos(swf, p['id']):
                    if k == 'frame' and t not in (0, fi) and t < len(tl.frames) and popup(t):
                        txt = [T(text_of(swf, c)) for c in button_texts(swf, p['id'])]
                        out_.append((t, txt[0] if txt else None))
        return out_

    hotspots = []
    for d, p in sorted(base.items()):
        if swf.chars[p['id']][0] != 'button':
            continue
        b = char_bounds(swf, p['id'], p['matrix'])
        tg = [t for k, t in button_gotos(swf, p['id']) if k == 'frame']
        if not tg or not popup(tg[0]):
            continue  # close buttons / dead links
        names = [T(text_of(swf, c)) for c in button_texts(swf, p['id'])]
        hotspots.append({'frame': tg[0], 'box': b, 'in_panel': in_panel(b), 'name': names[0] if names else None})

    reached = set()
    described = []

    def collect_pages(start):
        pages, queue = [], [start]
        while queue:
            fi = queue.pop(0)
            if fi in reached:
                continue
            reached.add(fi)
            tid, bids = popup(fi)
            title = T(text_of(swf, tid))[len(TITLE_PREFIX):].strip(' -')
            body = '\n\n'.join(T(text_of(swf, c)) for c in bids)
            pages.append({'frame': fi, 'label': tl.frames[fi]['label'], 'title': title, 'text': body})
            queue += [t for t, _ in popup_links(fi)]
        return pages

    # province itself
    reached.add(0)
    tid, bids = popup(0)
    text_of(swf, tid)
    prov_entry = {'id': pid, 'name': head_ko, 'hanja': head_hanja, 'short': name, 'province': pid, 'kind': '성',
                  'map': 'china', 'detail_map': pid,
                  'description': [{'title': head, 'text': '\n\n'.join(T(text_of(swf, c)) for c in bids)}]}

    for h in sorted(hotspots, key=lambda h: h['frame']):
        if h['frame'] in reached:
            # several buttons can open the same frame; keep first, just note extra hit area
            continue
        pages = collect_pages(h['frame'])
        if not pages:
            continue
        segs = [s.strip() for s in pages[0]['title'].split('-')]
        is_sect = any(s.startswith('무림문파') for s in segs)
        nm = segs[2] if is_sect and len(segs) > 2 else segs[-1]
        ko, hanja = split_name(nm)
        if h['name']:
            hk, hh = split_name(h['name'])
            ko, hanja = hk or ko, hh or hanja
        described.append({'hotspot': h, 'ko': ko, 'hanja': hanja, 'sect': is_sect, 'pages': pages})

    # merge descriptions into label entries (by name, else nearest label) or make new entries
    for i, dsc in enumerate(described):
        h = dsc['hotspot']
        match = next((e for e in entries if e['kind'] != '인접 지역' and e['name'] == dsc['ko']), None)
        if match is None and dsc['sect']:
            stem = re.sub(r'(파|세가|문|사|검파)$', '', dsc['ko'])
            match_loc = next((e for e in entries if e['kind'] != '인접 지역' and len(stem) >= 2
                              and e['name'].startswith(stem)), None)
        else:
            match_loc = None
        desc = [{'title': p['title'], 'text': p['text']} for p in dsc['pages']]
        if match is not None and not dsc['sect']:
            match['description'] = desc
            if h['frame'] == 1:
                match['kind'] = '성도'
            elif match['kind'] == '지명':
                match['kind'] = '명승지'
            continue
        if dsc['sect']:
            kind = '문파'
        elif h['frame'] == 1:
            kind = '성도'
        else:
            kind = '명승지' if dsc['hanja'].endswith(SIGHT_SUFFIX) else '도시'
        e = {'id': f'{pid}-f{h["frame"]}', 'name': dsc['ko'], 'hanja': dsc['hanja'], 'province': pid,
             'kind': kind, 'map': pid, 'description': desc}
        if not h['in_panel']:
            c = center(h['box'])
            near = [m for m in markers if box_dist(h['box'], *m) < 200]
            c = near[0] if near else c
            e['x'], e['y'] = px(c[0]), px(c[1])
            e['label'] = {'x': px(h['box'][0]), 'y': px(h['box'][1])}
            e['located'] = 'hotspot'
        else:
            # listed in a side panel: borrow a map position by name, else by the most-mentioned label
            loc, how = match_loc, 'name'
            if loc is None:
                body = ' '.join(d['text'] for d in desc)
                # hanja names are unambiguous; bare Hangul only for 3+ syllables
                def hits(x):
                    n = body.count(x['hanja']) if len(x['hanja']) >= 2 else 0
                    return n or (body.count(x['name']) if len(x['name']) >= 3 else 0)
                cands = [(hits(x), x) for x in entries
                         if x['kind'] in ('도시', '성도', '명승지', '지명') and x['name'] != dsc['ko']]
                cands = [(n, -body.find(x['hanja'] or x['name']), x) for n, x in cands if n]
                if cands:
                    loc, how = max(cands, key=lambda c: c[:2])[2], 'description'
            if loc is not None:
                e['x'], e['y'], e['near'], e['located'] = loc['x'], loc['y'], loc['id'], how
            else:
                e['x'] = e['y'] = None
        entries.append(e)

    unreached = [i for i, f in enumerate(tl.frames) if popup(i) and i not in reached]
    if unreached:
        report['unreached_frames'].append({'province': pid, 'frames': unreached,
                                           'labels': [tl.frames[i]['label'] for i in unreached]})
    return {'province': prov_entry, 'entries': entries, 'viewBox': vb}


# ---------------------------------------------------------------- 帝王年表

YEAR = r'(?:B\.C\.|A\.D\.)\s*\d{1,4}|\d{3,4}'


def emperors(swf):
    out = []
    menu = swf.root.frames[1]['display']
    for fi in range(2, 27):
        f = swf.root.frames[fi]
        texts = [(d, p['id']) for d, p in sorted(f['display'].items())
                 if is_text(swf, p['id']) and menu.get(d) != p]
        tables = [c for d, c in texts if '즉위' in swf.chars[c][1]['text']]
        if not tables:
            # 남북조 index page: just the heading
            for d, c in texts:
                text_of(swf, c)
            continue
        heads = [T(text_of(swf, c)) for d, c in texts if c not in tables]
        raw = T(text_of(swf, tables[0]))
        lines = raw.split('\n')
        title_ko, title_hanja = split_name(lines[0].strip().split('제왕')[0])
        period = next((re.search(r'\((\d+\s*~\s*\d+)\)', h).group(1).replace(' ', '')
                       for h in heads if re.search(r'\(\d+\s*~\s*\d+\)', h)), None)
        rows, group = [], None
        for ln in lines[1:]:
            if not ln.strip() or '즉위' in ln:
                continue
            years = re.findall(YEAR, ln)
            namepart = re.split(YEAR, ln)[0] if years else ln
            ko, hanja = split_name(namepart)
            years = [re.sub(r'\s+', '', y).replace('B.C.', 'BC ').replace('A.D.', 'AD ') for y in years]
            if not years:
                group = {'ko': ko, 'hanja': hanja}
                continue
            rows.append({'name': ko, 'hanja': hanja, 'start': years[0] if years else None,
                         'end': years[1] if len(years) > 1 else None,
                         'group': f'{group["ko"]}({group["hanja"]})' if group else None,
                         'raw': ln.strip()})
        out.append({'id': f'dyn{fi}', 'label': f['label'], 'name': title_ko, 'hanja': title_hanja,
                    'parent': '남북조' if f['label'].startswith('남북조-') else None,
                    'period': period, 'rows': rows, 'raw': raw})
    return out


# ---------------------------------------------------------------- 主要地名 and about

def landmarks(swf, places):
    out = []
    menu = swf.root.frames[27]['display']
    names = {}
    for e in places:
        if e.get('description') and e['kind'] != '인접 지역':
            names.setdefault(e['name'], e['id'])
    for fi in range(28, 34):
        f = swf.root.frames[fi]
        texts = [(d, p['id']) for d, p in sorted(f['display'].items()) if is_text(swf, p['id'])]
        body = [c for d, c in texts if '\r' in swf.chars[c][1]['text']]
        heading = [c for d, c in texts if c not in body and menu.get(d, {}).get('id') != c]
        heading = [T(text_of(swf, c)) for c in heading if T(swf.chars[c][1]['text']) != '주요지명']
        raw = '\n\n'.join(T(text_of(swf, c)) for c in body)
        title = heading[0] if heading else f['label']
        links = []
        for m in re.finditer(r'([가-힣]{2,6})\s*\[', raw):
            if m.group(1) in names and names[m.group(1)] not in links:
                links.append(names[m.group(1)])
        out.append({'id': f'lm{fi}', 'label': f['label'], 'title': title, 'text': raw, 'links': links})
    return out


def about(swf):
    f0 = swf.root.frames[0]['display']
    side = sorted(((p['matrix'][5], p['matrix'][4], p['id']) for d, p in f0.items()
                   if is_text(swf, p['id']) and d > 500))
    buttons = sorted(((p['matrix'][5], p['matrix'][4], p['id']) for d, p in f0.items()
                      if swf.chars[p['id']][0] == 'button' and d > 500))
    links = []
    for y, x, b in buttons:
        for c in button_texts(swf, b):
            links.append(T(text_of(swf, c)).strip("'").strip(','))
    notice = [T(text_of(swf, c)) for y, x, c in side]
    f48 = swf.root.frames[48]['display']
    author = [T(text_of(swf, p['id'])) for d, p in sorted(f48.items()) if is_text(swf, p['id'])]
    links = sorted(set(l.strip() for l in links if '://' in l or '@' in l))
    return {'notice': notice, 'links': links, 'author_note': author}


# ---------------------------------------------------------------- main

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else 'legacy/murim.swf'
    out = sys.argv[2] if len(sys.argv) > 2 else 'docs'
    os.makedirs(f'{out}/maps', exist_ok=True)
    os.makedirs(f'{out}/data', exist_ok=True)
    swf = SWF(src)
    report = {'placeholder_provinces': [], 'unreached_frames': []}

    provs, china_vb = national(swf, out)
    maps = [{'id': 'china', 'name': '중국전도', 'hanja': '中國全圖', 'svg': 'maps/china.svg', 'viewBox': china_vb}]
    places = []
    for name in sorted(provs, key=lambda n: provs[n]['frame']):
        info = provs[name]
        res = province(swf, name, info['frame'], out, report)
        c = center(info['bounds'])
        if res is None:
            hanja = ''
            places.append({'id': PROVINCE_IDS[name], 'name': name, 'hanja': hanja, 'short': name,
                           'province': PROVINCE_IDS[name], 'kind': '성', 'map': 'china', 'detail_map': None,
                           'x': px(c[0]), 'y': px(c[1]), 'description': None})
            continue
        pe = res['province']
        pe['x'], pe['y'] = px(c[0]), px(c[1])
        places.append(pe)
        places.extend(res['entries'])
        maps.append({'id': pe['id'], 'name': pe['name'], 'hanja': pe['hanja'], 'svg': f'maps/{pe["id"]}.svg',
                     'viewBox': res['viewBox']})

    # hanja for placeholder provinces from neighbour labels elsewhere
    for p in places:
        if p['kind'] == '성' and not p['hanja']:
            for q in places:
                if q['kind'] == '인접 지역' and q.get('link') == p['id']:
                    p['name'], p['hanja'] = q['name'], q['hanja']
                    break

    emp = emperors(swf)
    lms = landmarks(swf, places)
    ab = about(swf)

    def dump(name, obj):
        with open(f'{out}/data/{name}', 'w', encoding='utf-8') as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=1)
            fh.write('\n')

    dump('places.json', {'maps': maps, 'places': places})
    dump('emperors.json', emp)
    dump('landmarks.json', lms)
    dump('about.json', ab)

    all_texts = {c for c, (k, v) in swf.chars.items() if k == 'text'}
    left = sorted(all_texts - used_texts)
    stale_sprites = {swf.root.frames[provs[n]['frame']]['display'][3]['id']
                     for n in provs if PROVINCE_IDS[n] in {q['province'] for q in report['placeholder_provinces']}}
    in_button = {r['id'] for k, v in swf.chars.values() if k == 'button' for r in v['records']}
    in_stale = set()
    for sid in stale_sprites:
        for fr in swf.chars[sid][1].frames:
            in_stale |= {q['id'] for q in fr['display'].values()}
    for u in report['unreached_frames']:
        sid = swf.root.frames[provs[next(n for n in provs if PROVINCE_IDS[n] == u['province'])]['frame']]['display'][3]['id']
        for i in u['frames']:
            in_stale |= {q['id'] for q in swf.chars[sid][1].frames[i]['display'].values()}
    cats = Counter('stale_copy' if c in in_stale else 'ui_button' if c in in_button else 'ui_other' for c in left)
    report['unused_by_category'] = cats
    left_unique = Counter(T(swf.chars[c][1]['text']) for c in left)
    report.update({
        'maps': len(maps),
        'places_total': len(places),
        'kinds': Counter(p['kind'] for p in places),
        'with_description': sum(1 for p in places if p.get('description')),
        'without_coords': [p['id'] for p in places if p.get('x') is None],
        'emperor_tables': len(emp), 'emperor_rows': sum(len(e['rows']) for e in emp),
        'landmark_articles': len(lms),
        'texts_total': len(all_texts), 'texts_used': len(all_texts & used_texts),
        'texts_unused': len(left), 'texts_unused_unique': len(left_unique),
        'unused_samples': {cat: sorted({T(swf.chars[c][1]['text'])[:60] for c in left
                                        if ('stale_copy' if c in in_stale else 'ui_button' if c in in_button
                                            else 'ui_other') == cat}) for cat in cats},
    })
    dump('report.json', report)
    for k in ('maps', 'places_total', 'kinds', 'with_description', 'emperor_tables', 'emperor_rows',
              'landmark_articles', 'texts_total', 'texts_used', 'texts_unused', 'texts_unused_unique',
              'unused_by_category'):
        print(f'{k}: {report[k]}')
    print('placeholder provinces:', [p['name'] for p in report['placeholder_provinces']])
    print('without coords:', report['without_coords'])


if __name__ == '__main__':
    main()
