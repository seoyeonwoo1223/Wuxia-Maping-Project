'use strict';
/* 무협용 중국전도 — static viewer. Data: data/*.json, maps: maps/*.svg (px units, same space as place x/y). */

const SVGNS = 'http://www.w3.org/2000/svg';
const ISSUES = 'https://github.com/seoyeonwoo1223/Wuxia-Maping-Project/issues';
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const state = { maps: {}, places: [], byId: {}, emperors: [], landmarks: [], about: null, mapId: null, selected: null };
const svgCache = {};

/* ------------------------------------------------------------------ text */

// The original wraps lines at a fixed width; join wrapped lines back into paragraphs, keep list-like lines.
const LIST_START = /^\s*([-–·•◆◇■□○●※*▶▷>]|\d+[.)]|[(（]\d+[)）]|[가-힣A-Za-z0-9 ]{1,12}\s*:)/;
function prose(text) {
  const out = [];
  for (const block of String(text || '').split(/\n\s*\n/)) {
    // tidy stray blanks from the original layout: "a  b" -> "a b", "( x )" -> "(x)", "a ," -> "a,"
    const lines = block.split('\n').map(l => l.trim().replace(/[ \t]{2,}/g, ' ').replace(/([(\[]) +/g, '$1')
      .replace(/ +([)\],])/g, '$1')).filter(Boolean);
    const paras = [];
    for (const l of lines) {
      const prev = paras[paras.length - 1];
      if (prev && !LIST_START.test(l) && prev.text.length >= 40 && prev.last.length >= 40) {
        prev.text += ' ' + l; prev.last = l;
      } else {
        paras.push({ text: l, last: l, li: LIST_START.test(l) });
      }
    }
    for (const p of paras) {
      out.push(/^◆/.test(p.text) && p.text.length < 40
        ? `<h4>${esc(p.text)}</h4>`
        : `<p${p.li ? ' class="li"' : ''}>${esc(p.text)}</p>`);
    }
  }
  return `<div class="prose">${out.join('')}</div>`;
}

const nameHtml = p => `${esc(p.name)}${p.hanja ? `<span class="hj">${esc(p.hanja)}</span>` : ''}`;
const provName = id => (state.byId[id] ? state.byId[id].name : id);

/* ------------------------------------------------------------------ map: pan / zoom */

const svg = $('#map');
let view = null, fitBox = null;

function setView(v) {
  view = v;
  svg.setAttribute('viewBox', `${v.x} ${v.y} ${v.w} ${v.h}`);
  updateLabels();
}
function scale() { // screen px per map unit
  const r = svg.getBoundingClientRect();
  return Math.min(r.width / view.w, r.height / view.h);
}
function fit(box = fitBox) {
  const r = svg.getBoundingClientRect();
  const ar = r.width / r.height || 1;
  let w = box[2], h = box[3];
  if (w / h > ar) h = w / ar; else w = h * ar;
  setView({ x: box[0] - (w - box[2]) / 2, y: box[1] - (h - box[3]) / 2, w, h });
}
function clientToMap(cx, cy) {
  const r = svg.getBoundingClientRect(), s = scale();
  const ox = (r.width - view.w * s) / 2, oy = (r.height - view.h * s) / 2;
  return { x: view.x + (cx - r.left - ox) / s, y: view.y + (cy - r.top - oy) / s };
}
function zoomAt(k, cx, cy) {
  const minW = fitBox[2] / 12, maxW = fitBox[2] * 2.5;
  const nw = Math.min(maxW, Math.max(minW, view.w / k));
  k = view.w / nw;
  const p = clientToMap(cx, cy);
  setView({ x: p.x - (p.x - view.x) / k, y: p.y - (p.y - view.y) / k, w: view.w / k, h: view.h / k });
}
function zoomCenter(k) { const r = svg.getBoundingClientRect(); zoomAt(k, r.left + r.width / 2, r.top + r.height / 2); }
function centerOn(x, y, minScale = 1.6, sheet = false) {
  const r = svg.getBoundingClientRect();
  const s = Math.max(scale(), minScale);
  const w = r.width / s, h = r.height / s;
  // on phones the bottom sheet covers the lower part: put the point in the visible upper area
  const fy = sheet && isPhone() ? 0.2 : 0.5;
  setView({ x: x - w / 2, y: y - h * fy, w, h });
}
const isPhone = () => window.matchMedia('(max-width: 760px)').matches;

svg.addEventListener('wheel', e => {
  if (!view) return;
  e.preventDefault();
  zoomAt(Math.exp(-e.deltaY * (e.deltaMode ? 0.05 : 0.0015)), e.clientX, e.clientY);
}, { passive: false });

const pointers = new Map();
let drag = null, moved = 0;
svg.addEventListener('pointerdown', e => {
  if (!view) return;
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  moved = 0;
  drag = { view: { ...view }, pts: new Map(pointers) };
  svg.classList.add('dragging');
});
svg.addEventListener('pointermove', e => {
  if (!pointers.has(e.pointerId) || !drag) return;
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  const s = scale();
  if (pointers.size === 1) {
    const a = drag.pts.get(e.pointerId); if (!a) return;
    const dx = e.clientX - a.x, dy = e.clientY - a.y;
    moved = Math.max(moved, Math.abs(dx) + Math.abs(dy));
    // capture only once it is a drag, so plain clicks still reach provinces and labels
    if (moved > 4 && !svg.hasPointerCapture(e.pointerId)) svg.setPointerCapture(e.pointerId);
    setView({ ...drag.view, x: drag.view.x - dx / s, y: drag.view.y - dy / s });
  } else if (pointers.size === 2) {
    const [p1, p2] = [...pointers.values()];
    for (const id of pointers.keys()) if (!svg.hasPointerCapture(id)) svg.setPointerCapture(id);
    const [q1, q2] = [...drag.pts.values()];
    if (!q2) { drag.pts = new Map(pointers); drag.view = { ...view }; return; }
    const d0 = Math.hypot(q1.x - q2.x, q1.y - q2.y), d1 = Math.hypot(p1.x - p2.x, p1.y - p2.y);
    moved = 99;
    view = { ...drag.view };
    zoomAt(d1 / (d0 || 1), (p1.x + p2.x) / 2, (p1.y + p2.y) / 2);
  }
});
function endPointer(e) {
  pointers.delete(e.pointerId);
  drag = pointers.size ? { view: { ...view }, pts: new Map(pointers) } : null;
  if (!pointers.size) svg.classList.remove('dragging');
}
svg.addEventListener('pointerup', endPointer);
svg.addEventListener('pointercancel', endPointer);
// suppress clicks that ended a drag
svg.addEventListener('click', e => { if (moved > 6) { e.stopPropagation(); e.preventDefault(); } }, true);

$('#zin').onclick = () => zoomCenter(1.5);
$('#zout').onclick = () => zoomCenter(1 / 1.5);
$('#zfit').onclick = () => fit();
window.addEventListener('resize', () => { if (view && state.mapId) { const c = { x: view.x + view.w / 2, y: view.y + view.h / 2 }; const s = scale(); setView(view); centerOn(c.x, c.y, s); } });

/* ------------------------------------------------------------------ map: content */

let labelLayer = null;

async function loadSvg(id) {
  if (!svgCache[id]) {
    const res = await fetch(state.maps[id].svg);
    svgCache[id] = new DOMParser().parseFromString(await res.text(), 'image/svg+xml').documentElement;
  }
  return svgCache[id];
}

async function showMap(id) {
  if (state.mapId === id) return;
  const m = state.maps[id];
  const doc = await loadSvg(id);
  svg.replaceChildren(...[...doc.childNodes].map(n => document.importNode(n, true)));
  svg.setAttribute('aria-label', `${m.name} 지도`);
  svg.classList.toggle('detail', id !== 'china');
  $('#legend').hidden = id === 'china';
  state.mapId = id;
  fitBox = m.viewBox;
  if (id === 'china') decorateChina();
  labelLayer = document.createElementNS(SVGNS, 'g');
  labelLayer.setAttribute('class', 'labels');
  svg.appendChild(labelLayer);
  buildLabels(id);
  fit();
  renderCrumbs();
}

function decorateChina() {
  for (const g of svg.querySelectorAll('.province')) {
    const p = state.byId[g.dataset.id];
    if (!p) continue;
    if (!p.detail_map) g.classList.add(p.extra ? 'extra' : 'todo');
    const t = document.createElementNS(SVGNS, 'title');
    t.textContent = p.name + (p.detail_map ? '' : p.extra ? ' (보충 자료)' : ' (원작 미완성)');
    g.prepend(t);
    g.addEventListener('click', () => go(`#/place/${p.id}`));
  }
}

const labels = [];
function buildLabels(mapId) {
  labels.length = 0;
  placedScale = null;
  const items = state.places.filter(p => p.map === mapId && p.x != null && p.kind !== '성');
  for (const p of items) {
    const major = !!p.description;
    const nb = p.kind === '인접 지역';
    const g = document.createElementNS(SVGNS, 'g');
    let ring = null;
    if (major && !nb) {
      ring = document.createElementNS(SVGNS, 'circle');
      ring.setAttribute('class', 'mk');
      g.appendChild(ring);
    }
    const t = document.createElementNS(SVGNS, 'text');
    t.setAttribute('class', `lbl ${nb ? 'nb' : major ? 'major' : 'minor'}`);
    t.innerHTML = `${esc(p.name)}${p.hanja && !nb ? `<tspan class="hj"> ${esc(p.hanja)}</tspan>` : ''}`;
    g.appendChild(t);
    // keep the original side of the label relative to its marker
    const left = !nb && p.label && p.label.x < p.x - 4;
    g.addEventListener('click', e => { e.stopPropagation(); go(nb && p.link ? `#/map/${p.link}` : `#/place/${p.id}`); });
    labelLayer.appendChild(g);
    labels.push({ p, g, t, ring, left, nb, major });
  }
}

// text widths at font-size 1, measured once per label (canvas, same font as the map labels)
const measureCtx = document.createElement('canvas').getContext('2d');
function textWidth(str, weight) {
  measureCtx.font = `${weight} 100px "Noto Sans KR", sans-serif`;
  return measureCtx.measureText(str).width / 100;
}

let placedScale = null;
// once the web font arrives, widths change: measure again
if (document.fonts) document.fonts.ready.then(() => { for (const L of labels) L.w = null; placedScale = null; if (view) updateLabels(); });
function updateLabels() {
  if (!labelLayer) return;
  const s = scale();
  svg.classList.toggle('hide-minor', s < 0.95);
  svg.classList.toggle('hide-hanja', s < 1.8);
  for (const L of labels) {
    const { p, t, ring } = L;
    const fs = (L.major ? 13.5 : L.nb ? 12 : 11.5) / s;
    L.fs = fs;
    t.setAttribute('font-size', fs.toFixed(3));
    t.setAttribute('stroke-width', (3 / s).toFixed(3));
    t.setAttribute('dominant-baseline', 'central');
    if (ring) {
      ring.setAttribute('cx', p.x); ring.setAttribute('cy', p.y);
      ring.setAttribute('r', (7 / s).toFixed(3));
      ring.setAttribute('stroke-width', (2 / s).toFixed(3));
    }
    const sel = state.selected === p.id;
    t.classList.toggle('sel', sel);
    if (ring) ring.classList.toggle('sel', sel);
  }
  // panning keeps the layout; only a zoom change (or a new selection) needs a fresh placement
  const key = `${s.toFixed(4)}|${state.selected}`;
  if (key !== placedScale) { placedScale = key; placeLabels(s); }
}

// Greedy label placement: important labels first, each takes the first of right / left / above / below
// that hits neither an already placed label nor another city dot. Minor labels with no room are hidden.
function placeLabels(s) {
  const showHanja = s >= 1.8, showMinor = s >= 0.95;
  const boxes = [];
  const dot = 4 / s, pad = 1.5 / s;
  const dots = labels.filter(L => !L.nb).map(L => [L.p.x - dot, L.p.y - dot, L.p.x + dot, L.p.y + dot, L]);
  const hit = (b, self) => boxes.some(o => b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1])
    || dots.some(d => d[4] !== self && b[0] < d[2] && b[2] > d[0] && b[1] < d[3] && b[3] > d[1]);
  const rank = L => (state.selected === L.p.id ? 0 : L.major ? 1 : L.nb ? 3 : 2);
  const order = labels.slice().sort((a, b) => rank(a) - rank(b));
  for (const L of order) {
    const { p, t } = L;
    const visible = !(L.minorHidden = !L.major && !L.nb && !showMinor);
    if (!visible) { t.style.display = ''; continue; }
    if (L.w == null) {
      const w8 = L.major ? 700 : 400;
      L.w = textWidth(p.name, w8);
      L.wh = p.hanja && !L.nb ? textWidth(' ' + p.hanja, 400) : 0;
    }
    const fs = L.fs, w = (L.w + (showHanja ? L.wh : 0)) * fs, h = fs * 1.15;
    let cands;
    if (L.nb) {
      cands = [['middle', p.x, p.y]];
    } else {
      const off = (L.major ? 9 : 5) / s;
      const right = ['start', p.x + off, p.y], left = ['end', p.x - off, p.y];
      cands = [...(L.left ? [left, right] : [right, left]),
        ['middle', p.x, p.y - off - h / 2], ['middle', p.x, p.y + off + h / 2]];
    }
    let chosen = null;
    for (const c of cands) {
      const [anchor, x, y] = c;
      const x0 = anchor === 'start' ? x : anchor === 'end' ? x - w : x - w / 2;
      const b = [x0 - pad, y - h / 2 - pad, x0 + w + pad, y + h / 2 + pad];
      if (!hit(b, L)) { chosen = [c, b]; break; }
    }
    if (!chosen && (L.major || L.nb || rank(L) === 0)) {
      const c = cands[0], [anchor, x, y] = c;
      const x0 = anchor === 'start' ? x : anchor === 'end' ? x - w : x - w / 2;
      chosen = [c, [x0, y - h / 2, x0 + w, y + h / 2]];
    }
    if (!chosen) { t.style.display = 'none'; continue; }
    t.style.display = '';
    const [[anchor, x, y], b] = chosen;
    t.setAttribute('x', x); t.setAttribute('y', y); t.setAttribute('text-anchor', anchor);
    boxes.push(b);
  }
}

function renderCrumbs() {
  const m = state.maps[state.mapId];
  $('#crumbs').innerHTML = state.mapId === 'china'
    ? `<span>중국전도</span><span class="note">· 성을 누르면 상세 지도</span>`
    : `<a href="#/">중국전도</a><span>›</span><span>${esc(m.name)}</span>`;
}

/* ------------------------------------------------------------------ panel */

const panel = $('#panel');
$('#grip').onclick = () => panel.classList.toggle('open');
// corrected text by default; the original stays one click away
let showOrig = false, rerender = null;
const pageText = d => (showOrig && d.orig != null ? d.orig : d.text);
function corrNote(pages) {
  if (!pages.some(d => d.orig != null)) return '';
  return `<p class="note corr">${showOrig ? '원작 원문을 보고 있습니다.' : '오탈자와 어색한 문장을 일부 다듬은 글입니다.'}
    <button type="button" class="linklike" id="orig-toggle">${showOrig ? '다듬은 글 보기' : '원문 보기'}</button></p>`;
}
function bindCorrToggle(fn, root = panel) {
  rerender = fn;
  const b = root.querySelector('#orig-toggle');
  if (b) b.onclick = () => { showOrig = !showOrig; rerender(); };
}

function setPanel(html, open = true) {
  $('#panel-body').innerHTML = html;
  panel.scrollTop = 0;
  panel.classList.toggle('open', open);
}

function placeList(items) {
  return `<ul class="list">${items.map(p =>
    `<li><a href="#/place/${p.id}"><span>${nameHtml(p)}</span><span class="k">${esc(p.kind)}${p.x == null ? ' · 위치 미상' : ''}</span></a></li>`).join('')}</ul>`;
}

const KIND_ORDER = { '성도': 0, '문파': 1, '세력': 2, '명승지': 3, '무공': 4, '인물': 5, '도시': 6, '지명': 7 };
function describedIn(pid) {
  return state.places.filter(p => p.province === pid && p.kind !== '성' && p.description)
    .sort((a, b) => (KIND_ORDER[a.kind] ?? 9) - (KIND_ORDER[b.kind] ?? 9));
}

function panelChina() {
  const provs = state.places.filter(p => p.kind === '성').sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  setPanel(`
    <h2>중국전도<span class="hj">中國全圖</span></h2>
    <p class="note">2003년 낙방수재가 만든 「무협용 중국전도 Ver. 2.0」을 다시 정리한 지도입니다. 성을 누르면 성별 지도와 지명·문파 설명이 열립니다.</p>
    <div class="section-h">성 목록</div>
    <ul class="list">${provs.map(p => `<li><a href="#/place/${p.id}"><span>${nameHtml(p)}</span><span class="k">${p.detail_map ? `설명 ${describedIn(p.id).length}` : p.extra ? '보충 자료' : '원작 미완성'}</span></a></li>`).join('')}</ul>
  `, false);
}

const sourcesHtml = list => `<div class="section-h">참고 자료</div><ul class="list">${list.map(s =>
  `<li><a href="${esc(s.url)}" rel="noopener" target="_blank"><span>${esc(s.title)}</span><span class="k">↗</span></a></li>`).join('')}</ul>`;
const SUPPLEMENT_NOTE = `<p class="note">원작(Ver. 2.0)에는 없던 지역이라, 이 프로젝트에서 보충한 글입니다. 원작 내용이 아니며 상세 지도도 없습니다.</p>`;

function panelProvince(p) {
  if (!p.detail_map && p.extra) {
    const items = describedIn(p.id);
    setPanel(`<h2>${nameHtml(p)}</h2><div class="meta"><span class="chip k">성</span><span class="chip">보충 자료</span></div>
      ${SUPPLEMENT_NOTE}
      ${p.extra.description.map(d => prose(d.text)).join('')}
      ${items.length ? `<div class="section-h">문파·세력·명소 · ${items.length}</div>${placeList(items)}` : ''}
      ${sourcesHtml(p.extra.sources)}`);
    return;
  }
  if (!p.detail_map) {
    setPanel(`<h2>${nameHtml(p)}</h2><div class="meta"><span class="chip k">성</span></div>
      <p>원작(Ver. 2.0)에서 “여기는 아직 준비중이라오.”로 남아 있던 지역이라 상세 지도와 설명이 없습니다.</p>
      <p class="note">원본 파일에는 이 자리에 광서성 지도가 복사되어 있어 옮기지 않았습니다.</p>`);
    return;
  }
  const items = describedIn(p.id);
  setPanel(`
    <h2>${nameHtml(p)}</h2>
    <div class="meta"><span class="chip k">성</span></div>
    ${state.mapId !== p.id ? `<a class="btn" href="#/map/${p.id}">상세 지도 보기</a>` : ''}
    ${corrNote(p.description || [])}
    ${(p.description || []).map(d => prose(pageText(d))).join('')}
    ${items.length ? `<div class="section-h">설명이 있는 곳 · ${items.length}</div>${placeList(items)}` : ''}
  `, state.mapId !== p.id);
  bindCorrToggle(() => panelProvince(p));
}

function panelPlace(p) {
  const prov = state.byId[p.province];
  const pages = p.description || [];
  const near = p.near && state.byId[p.near];
  const sameName = state.places.filter(q => q !== p && q.description && q.name === p.name && q.kind !== '인접 지역');
  // pages that share a title in the original (e.g. 화산파 1/2) get a running number
  const raw = pages.map(d => pageTitle(d.title, p));
  const titles = raw.map((t, i) => (raw.filter(x => x === t).length > 1 ? `${t} ${raw.slice(0, i + 1).filter(x => x === t).length}` : t));
  setPanel(`
    <h2>${nameHtml(p)}</h2>
    <div class="meta">
      <span class="chip k">${esc(p.kind)}</span>
      ${prov ? `<a class="chip" href="#/place/${prov.id}">${esc(prov.name)}</a>` : ''}
    </div>
    ${p.supplement ? SUPPLEMENT_NOTE.replace('지역이라', '지역의 항목이라').replace(' 상세 지도도 없습니다', ' 지도 위치는 없습니다') : p.x == null ? `<p class="note">원작의 목록에만 있고 지도 위치가 없는 항목입니다.</p>` : ''}
    ${near && p.located === 'description' ? `<p class="note">지도 위치는 설명에 나오는 ‘${esc(near.name)}’ 기준의 대략적인 위치입니다.</p>` : ''}
    ${corrNote(pages)}
    ${pages.length > 1 ? `<div class="pages-nav">${pages.map((d, i) => `<a class="chip" href="#pg${i}" data-pg="${i}">${esc(titles[i])}</a>`).join('')}</div>` : ''}
    ${pages.map((d, i) => `${pages.length > 1 ? `<div class="page-title" id="pg${i}">${esc(titles[i])}</div>` : ''}${prose(pageText(d))}`).join('')}
    ${!pages.length ? `<p class="note">원작에 별도 설명이 없는 지명입니다.</p>` : ''}
    ${sameName.length ? `<div class="section-h">같은 이름</div>${placeList(sameName)}` : ''}
    ${p.supplement && prov && prov.extra ? sourcesHtml(prov.extra.sources) : ''}
  `);
  for (const a of panel.querySelectorAll('[data-pg]')) {
    a.onclick = e => { e.preventDefault(); panel.querySelector('#pg' + a.dataset.pg).scrollIntoView({ behavior: 'smooth' }); };
  }
  bindCorrToggle(() => panelPlace(p));
}

// "하남성(河南省) - 무림문파(武林門派) - 소림무공(少林武功) - 역근경(易筋經)" -> "소림무공 · 역근경(易筋經)"
function pageTitle(title, p) {
  const segs = title.split(' - ').map(s => s.trim()).filter(Boolean);
  const rest = segs.slice(1).filter(s => !s.startsWith('무림문파'));
  return rest.length ? rest.join(' · ') : title;
}

/* ------------------------------------------------------------------ text pages */

const page = $('#view-page');

function showPage(html) {
  $('#view-map').hidden = true;
  page.hidden = false;
  page.innerHTML = `<div class="page-inner">${html}</div>`;
  page.scrollTop = 0;
}

let empOrig = false;
function pageEmperors(id) {
  const list = state.emperors;
  const cur = list.find(d => d.id === id) || list[0];
  const tops = list.filter(d => !d.parent);
  const subs = list.filter(d => d.parent === '남북조');
  const tab = (d, cls = '') => `<a href="#/emperors/${d.id}" class="${cls}${d === cur ? ' on' : ''}">${esc(d.name)}${d.hanja ? ` ${esc(d.hanja)}` : ''}</a>`;
  let rows = '', grp = null;
  const fixed = cur.rows !== cur.orig;
  for (const r of (fixed && empOrig ? cur.orig : cur.rows)) {
    if (r.group && r.group !== grp) { grp = r.group; rows += `<tr class="grp"><td colspan="3">${esc(grp)}</td></tr>`; }
    rows += `<tr><td>${esc(r.name || '—')}${r.hanja ? `<span class="hj">${esc(r.hanja)}</span>` : ''}</td><td class="y">${esc(r.start || '')}</td><td class="y">${esc(r.end || '')}</td></tr>`;
  }
  showPage(`
    <h1>제왕연표<span class="hj">帝王年表</span></h1>
    <p class="lead">주(周)부터 청(淸)까지 왕조별 제왕과 재위 기간. 원작의 표를 옮기면서 깨진 글자와 오기를 바로잡았으며, 원작 표는 각 왕조의 [원문보기]로 볼 수 있습니다.</p>
    <div class="tabs">${tops.map(d => tab(d)).join('')}</div>
    ${subs.length ? `<div class="tabs"><span class="note">남북조:</span>${subs.map(d => tab(d, 'sub')).join('')}</div>` : ''}
    <h2>${esc(cur.name)}${cur.hanja ? `<span class="hj">${esc(cur.hanja)}</span>` : ''}${cur.period ? ` <span class="note">(${esc(cur.period)})</span>` : ''}${fixed ? ` <button class="linklike orig-small" id="emp-orig">[${empOrig ? '교정본 보기' : '원문보기'}]</button>` : ''}</h2>
    <table class="emp"><thead><tr><th>제왕</th><th>즉위</th><th>퇴위</th></tr></thead><tbody>${rows}</tbody></table>
  `);
  const b = $('#emp-orig');
  if (b) b.onclick = () => { empOrig = !empOrig; pageEmperors(cur.id); };
}

function pageLandmarks(id) {
  const cur = state.landmarks.find(l => l.id === id) || state.landmarks[0];
  showPage(`
    <h1>주요지명<span class="hj">主要地名</span></h1>
    <p class="lead">원작의 ‘주요지명’ 항목. 원작에 실린 명승지 사진은 출처가 확인되지 않아 싣지 않았습니다.</p>
    <div class="tabs">${state.landmarks.map(l => `<a href="#/landmarks/${l.id}" class="${l === cur ? 'on' : ''}">${esc(l.title)}</a>`).join('')}</div>
    <div class="card">
      <h2 style="margin-top:0">${esc(cur.title)}</h2>
      ${corrNote([cur])}
      ${prose(pageText(cur))}
      ${cur.links.length ? `<div class="section-h">지도에서 보기</div>${placeList(cur.links.map(i => state.byId[i]).filter(Boolean))}` : ''}
    </div>
  `);
  bindCorrToggle(() => pageLandmarks(cur.id), page);
}

function pageAbout() {
  const a = state.about;
  const sources = a.links.filter(l => l.startsWith('http'));
  showPage(`
    <h1>정보</h1>
    <div class="card">
      <h2 style="margin-top:0">원작</h2>
      <p><b>「무협용 중국전도 Ver. 2.0」</b> (2003, Flash) — 만든이 <b>낙방수재</b> (<a href="http://www.newmurim.com" rel="noopener">www.newmurim.com</a>)</p>
      <p>원작 고지: “이 지도는 누구나 사용할 수 있고, 누구나 재배포 할 수 있습니다.”</p>
      <p>원작에 적힌 자료 출처: ${sources.map(s => esc(s.replace(/^https?:\/\//, ''))).join(', ')}</p>
      <p class="note">원작은 내용이 다소 사실과 다를 수 있음을 밝히고 있습니다. 이 사이트는 원작의 지도와 글을 옮겨 정리했을 뿐 내용을 고치지 않았습니다.</p>
    </div>
    <div class="card">
      <h2 style="margin-top:0">문제 신고</h2>
      <p>저작권 등 문제가 되는 내용이 있으면 <a href="${ISSUES}" rel="noopener">GitHub 이슈</a>로 알려 주세요. 확인 후 수정하거나 삭제합니다.</p>
    </div>
    <div class="card">
      <h2 style="margin-top:0">이 사이트</h2>
      <p>원본 SWF에서 벡터 지도와 텍스트를 추출해 정적 웹 페이지로 다시 만들었습니다. 원작의 명승지 사진(제3자 사진으로 보임)은 싣지 않았습니다. 원작에서 미완성이던 북경·천진·중경은 이 프로젝트에서 따로 쓴 보충 글을 ‘보충 자료’로 표시해 실었습니다. 원작 설명 글의 오탈자와 어색한 문장은 조금씩 다듬고 있으며, 설명 패널의 ‘원문 보기’로 원작 그대로의 글을 볼 수 있습니다. 글꼴: Noto Sans KR, Noto Serif KR (SIL Open Font License).</p>
      <p><a href="https://github.com/seoyeonwoo1223/Wuxia-Maping-Project" rel="noopener">소스 저장소</a></p>
    </div>
    <h2>원작자의 말</h2>
    <div class="card">${a.author_note.map(prose).join('')}</div>
    <h2>원작 첫 화면 고지</h2>
    <div class="card">${a.notice.map(prose).join('')}</div>
  `);
}

/* ------------------------------------------------------------------ search */

const q = $('#q'), results = $('#results');
let hits = [], cursor = -1;
const norm = s => String(s || '').replace(/\s+/g, '').toLowerCase();

function search(term) {
  const t = norm(term);
  if (!t) return [];
  const scored = [];
  for (const p of state.places) {
    if (p.kind === '인접 지역') continue;
    const n = norm(p.name), h = norm(p.hanja);
    let s = n === t || h === t ? 0 : n.startsWith(t) || h.startsWith(t) ? 1 : n.includes(t) || h.includes(t) ? 2 : -1;
    if (s < 0 && p.description && t.length >= 2 && p.description.some(d => norm(d.text).includes(t))) s = 4;
    if (s < 0) continue;
    if (p.description) s -= 0.5;
    scored.push([s, p]);
  }
  scored.sort((a, b) => a[0] - b[0] || a[1].name.length - b[1].name.length);
  return scored.slice(0, 40).map(x => ({ p: x[1], body: x[0] >= 3 }));
}

function renderResults() {
  if (!q.value.trim()) { results.hidden = true; return; }
  results.hidden = false;
  results.innerHTML = hits.length
    ? hits.map((h, i) => `<li role="option" data-i="${i}" aria-selected="${i === cursor}">
        <span class="r-name">${esc(h.p.name)}</span>${h.p.hanja ? `<span class="r-hanja">${esc(h.p.hanja)}</span>` : ''}
        <span class="r-meta">${esc(h.p.kind)} · ${esc(provName(h.p.province))}${h.p.supplement ? ' · 보충' : ''}${h.body ? ' · 본문에 언급' : ''}</span></li>`).join('')
    : `<li class="r-empty">결과 없음</li>`;
}
function pick(i) {
  const h = hits[i]; if (!h) return;
  results.hidden = true; q.blur();
  go(`#/place/${h.p.id}`);
}
q.addEventListener('input', () => { hits = search(q.value); cursor = hits.length ? 0 : -1; renderResults(); });
q.addEventListener('keydown', e => {
  if (e.key === 'ArrowDown') { cursor = Math.min(hits.length - 1, cursor + 1); renderResults(); e.preventDefault(); }
  else if (e.key === 'ArrowUp') { cursor = Math.max(0, cursor - 1); renderResults(); e.preventDefault(); }
  else if (e.key === 'Enter') pick(cursor);
  else if (e.key === 'Escape') { results.hidden = true; }
});
q.addEventListener('focus', () => { if (q.value.trim()) renderResults(); });
results.addEventListener('pointerdown', e => { const li = e.target.closest('li[data-i]'); if (li) { e.preventDefault(); pick(+li.dataset.i); } });
document.addEventListener('pointerdown', e => { if (!e.target.closest('.search')) results.hidden = true; });

/* ------------------------------------------------------------------ routing */

function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }

async function route() {
  const [, kind = '', id = ''] = decodeURIComponent(location.hash.replace(/^#/, '')).split('/');
  for (const a of document.querySelectorAll('[data-nav]')) {
    a.classList.toggle('on', a.dataset.nav === (['emperors', 'landmarks', 'about'].includes(kind) ? kind : 'map'));
  }
  if (kind === 'emperors') return pageEmperors(id);
  if (kind === 'landmarks') return pageLandmarks(id);
  if (kind === 'about') return pageAbout();

  page.hidden = true;
  $('#view-map').hidden = false;
  state.selected = null;
  if (kind === 'map' && state.maps[id]) {
    await showMap(id);
    fit();
    const p = state.byId[id];
    if (p && p.kind === '성') panelProvince(p); else panelChina();
  } else if (kind === 'place' && state.byId[id]) {
    const p = state.byId[id];
    if (p.kind === '성') {
      await showMap('china');
      for (const g of svg.querySelectorAll('.province')) g.classList.toggle('on', g.dataset.id === p.id);
      panelProvince(p);
    } else {
      await showMap(p.map);
      state.selected = p.id;
      if (p.x != null) centerOn(p.x, p.y, Math.max(1.4, scale()), true); else fit();
      updateLabels();
      panelPlace(p);
    }
  } else {
    await showMap('china');
    for (const g of svg.querySelectorAll('.province')) g.classList.remove('on');
    panelChina();
  }
  document.title = state.selected ? `${state.byId[state.selected].name} — 무협용 중국전도` : '무협용 중국전도';
}

async function init() {
  const [pl, emp, lm, ab, sup, corr] = await Promise.all(
    ['places', 'emperors', 'landmarks', 'about', 'supplement', 'corrections'].map(n => fetch(`data/${n}.json`).then(r => r.json())));
  for (const m of pl.maps) state.maps[m.id] = m;
  state.places = pl.places;
  for (const p of pl.places) state.byId[p.id] = p;
  // proofreading layer over the extracted text (tools/check_corrections.py validates it)
  for (const ed of corr.edits) {
    const field = ed.field || 'text';
    // ids are place ids, or landmark article ids (lm28…) whose text/title sit on the article itself
    const article = lm.find(l => l.id === ed.id);
    const place = state.byId[ed.id];
    const obj = article || (field === 'name' || field === 'hanja' ? place : ((place || {}).description || [])[ed.page]);
    if (!obj || typeof obj[field] !== 'string' || obj[field].split(ed.find).length !== 2) { console.warn('correction not applied', ed); continue; }
    if (field === 'text' && obj.orig == null) obj.orig = obj.text;
    obj[field] = obj[field].replace(ed.find, () => ed.replace);
  }
  // hand-written supplement for regions the original left unfinished (kept apart from extracted data)
  for (const [id, x] of Object.entries(sup.provinces)) {
    const p = state.byId[id];
    if (!p) continue;
    p.name = x.name; p.hanja = x.hanja;
    p.extra = { description: x.description, sources: x.sources };
  }
  for (const x of sup.places) {
    const p = { ...x, map: 'china', x: null, y: null, supplement: true };
    state.places.push(p); state.byId[p.id] = p;
  }
  // emperor table fixes: rows addressed by their index in the original dynasty table
  for (const d of emp) d.orig = d.rows;
  for (const ed of corr.emperors || []) {
    const d = emp.find(x => x.id === ed.dyn);
    if (!d) { console.warn('emperor correction not applied', ed); continue; }
    if (d.rows === d.orig) d.rows = d.orig.map(r => ({ ...r }));
    if (ed.append) { d.rows.push(...ed.append.map(r => ({ ...r, added: true }))); continue; }
    const r = d.rows[ed.row];
    if (!r || d.orig[ed.row].name !== ed.expect) { console.warn('emperor correction not applied', ed); continue; }
    if (ed.delete) r.deleted = true; else Object.assign(r, ed.set);
  }
  for (const d of emp) d.rows = d.rows.filter(r => !r.deleted);
  state.emperors = emp; state.landmarks = lm; state.about = ab;
  window.addEventListener('hashchange', route);
  route();
}
init();
