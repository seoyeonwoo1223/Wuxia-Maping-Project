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
    const lines = block.split('\n').map(l => l.trim()).filter(Boolean);
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

function updateLabels() {
  if (!labelLayer) return;
  const s = scale();
  svg.classList.toggle('hide-minor', s < 0.95);
  svg.classList.toggle('hide-hanja', s < 1.8);
  for (const L of labels) {
    const { p, t, ring } = L;
    const fs = (L.major ? 13.5 : L.nb ? 12 : 11.5) / s;
    t.setAttribute('font-size', fs.toFixed(3));
    t.setAttribute('stroke-width', (3 / s).toFixed(3));
    if (L.nb) {
      t.setAttribute('x', p.x); t.setAttribute('y', p.y);
      t.setAttribute('text-anchor', 'middle');
    } else {
      const off = (L.major ? 9 : 5) / s;
      t.setAttribute('x', L.left ? p.x - off : p.x + off);
      t.setAttribute('y', p.y);
      t.setAttribute('text-anchor', L.left ? 'end' : 'start');
    }
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
    ${(p.description || []).map(d => prose(d.text)).join('')}
    ${items.length ? `<div class="section-h">설명이 있는 곳 · ${items.length}</div>${placeList(items)}` : ''}
  `, state.mapId !== p.id);
}

function panelPlace(p) {
  const prov = state.byId[p.province];
  const pages = p.description || [];
  const near = p.near && state.byId[p.near];
  const sameName = state.places.filter(q => q !== p && q.description && q.name === p.name && q.kind !== '인접 지역');
  setPanel(`
    <h2>${nameHtml(p)}</h2>
    <div class="meta">
      <span class="chip k">${esc(p.kind)}</span>
      ${prov ? `<a class="chip" href="#/place/${prov.id}">${esc(prov.name)}</a>` : ''}
    </div>
    ${p.supplement ? SUPPLEMENT_NOTE.replace('지역이라', '지역의 항목이라').replace(' 상세 지도도 없습니다', ' 지도 위치는 없습니다') : p.x == null ? `<p class="note">원작의 목록에만 있고 지도 위치가 없는 항목입니다.</p>` : ''}
    ${near && p.located === 'description' ? `<p class="note">지도 위치는 설명에 나오는 ‘${esc(near.name)}’ 기준의 대략적인 위치입니다.</p>` : ''}
    ${pages.length > 1 ? `<div class="pages-nav">${pages.map((d, i) => `<a class="chip" href="#pg${i}" data-pg="${i}">${esc(pageTitle(d.title, p))}</a>`).join('')}</div>` : ''}
    ${pages.map((d, i) => `${pages.length > 1 ? `<div class="page-title" id="pg${i}">${esc(pageTitle(d.title, p))}</div>` : ''}${prose(d.text)}`).join('')}
    ${!pages.length ? `<p class="note">원작에 별도 설명이 없는 지명입니다.</p>` : ''}
    ${sameName.length ? `<div class="section-h">같은 이름</div>${placeList(sameName)}` : ''}
    ${p.supplement && prov && prov.extra ? sourcesHtml(prov.extra.sources) : ''}
  `);
  for (const a of panel.querySelectorAll('[data-pg]')) {
    a.onclick = e => { e.preventDefault(); panel.querySelector('#pg' + a.dataset.pg).scrollIntoView({ behavior: 'smooth' }); };
  }
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

function pageEmperors(id) {
  const list = state.emperors;
  const cur = list.find(d => d.id === id) || list[0];
  const tops = list.filter(d => !d.parent);
  const subs = list.filter(d => d.parent === '남북조');
  const tab = (d, cls = '') => `<a href="#/emperors/${d.id}" class="${cls}${d === cur ? ' on' : ''}">${esc(d.name)}${d.hanja ? ` ${esc(d.hanja)}` : ''}</a>`;
  let rows = '', grp = null;
  for (const r of cur.rows) {
    if (r.group && r.group !== grp) { grp = r.group; rows += `<tr class="grp"><td colspan="3">${esc(grp)}</td></tr>`; }
    rows += `<tr><td>${esc(r.name || '—')}${r.hanja ? `<span class="hj">${esc(r.hanja)}</span>` : ''}</td><td class="y">${esc(r.start || '')}</td><td class="y">${esc(r.end || '')}</td></tr>`;
  }
  showPage(`
    <h1>제왕연표<span class="hj">帝王年表</span></h1>
    <p class="lead">주(周)부터 청(淸)까지 왕조별 제왕과 재위 기간. 원작의 표를 그대로 옮겼으며, 원본에서 깨져 있던 글자는 ‘?’로 남겨 두었습니다.</p>
    <div class="tabs">${tops.map(d => tab(d)).join('')}</div>
    ${subs.length ? `<div class="tabs"><span class="note">남북조:</span>${subs.map(d => tab(d, 'sub')).join('')}</div>` : ''}
    <h2>${esc(cur.name)}${cur.hanja ? `<span class="hj">${esc(cur.hanja)}</span>` : ''}${cur.period ? ` <span class="note">(${esc(cur.period)})</span>` : ''}</h2>
    <table class="emp"><thead><tr><th>제왕</th><th>즉위</th><th>퇴위</th></tr></thead><tbody>${rows}</tbody></table>
  `);
}

function pageLandmarks(id) {
  const cur = state.landmarks.find(l => l.id === id) || state.landmarks[0];
  showPage(`
    <h1>주요지명<span class="hj">主要地名</span></h1>
    <p class="lead">원작의 ‘주요지명’ 항목. 원작에 실린 명승지 사진은 출처가 확인되지 않아 싣지 않았습니다.</p>
    <div class="tabs">${state.landmarks.map(l => `<a href="#/landmarks/${l.id}" class="${l === cur ? 'on' : ''}">${esc(l.title)}</a>`).join('')}</div>
    <div class="card">
      <h2 style="margin-top:0">${esc(cur.title)}</h2>
      ${prose(cur.text)}
      ${cur.links.length ? `<div class="section-h">지도에서 보기</div>${placeList(cur.links.map(i => state.byId[i]).filter(Boolean))}` : ''}
    </div>
  `);
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
      <p>원본 SWF에서 벡터 지도와 텍스트를 추출해 정적 웹 페이지로 다시 만들었습니다. 원작의 명승지 사진(제3자 사진으로 보임)은 싣지 않았습니다. 원작에서 미완성이던 북경·천진·중경은 이 프로젝트에서 따로 쓴 보충 글을 ‘보충 자료’로 표시해 실었습니다. 글꼴: Noto Sans KR, Noto Serif KR (SIL Open Font License).</p>
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
  const [pl, emp, lm, ab, sup] = await Promise.all(
    ['places', 'emperors', 'landmarks', 'about', 'supplement'].map(n => fetch(`data/${n}.json`).then(r => r.json())));
  for (const m of pl.maps) state.maps[m.id] = m;
  state.places = pl.places;
  for (const p of pl.places) state.byId[p.id] = p;
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
  state.emperors = emp; state.landmarks = lm; state.about = ab;
  window.addEventListener('hashchange', route);
  route();
}
init();
