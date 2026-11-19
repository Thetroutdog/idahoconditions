// Static region-map data: ski areas, major towns, national parks/monuments/reserves, and main rivers. No live data on purpose.
// Only ski areas with trusted coordinates (place-level or manual) are pinned; town-level ones would land in the wrong place.
import fs from 'node:fs';
import path from 'node:path';
import { spotsIn } from './catalog.js';
import { projectPoint } from './regionview.js';
import map from '../data/idaho-map.json';
import riverData from '../data/idaho-rivers.json';

const read = (f) => { try { return JSON.parse(fs.readFileSync(path.resolve(process.cwd(), 'data', f), 'utf8')); } catch { return {}; } };
const coords = read('spot_coords.json').spots ?? {};
const manualRaw = read('spot_coords_manual.json');
const manual = manualRaw.spots ?? manualRaw;
const towns = read('map_towns.json').towns ?? [];
const landmarks = read('map_landmarks.json').landmarks ?? [];

const trusted = (id) => {
  if (manual[id]?.lat != null) return manual[id];
  const c = coords[id];
  return c && c.precision === 'place' ? c : null;
};
const shortName = (n) => n.replace(/\s*\(.*?\)/g, '').trim();

// "M x,y L x,y ... Z M ..." -> array of rings of [x, y]
const rings = (d) => d.split('M').filter(Boolean).map((seg) => seg.replace(/[LZ]/g, ' ').trim().split(/\s+/).map((p) => p.split(',').map(Number)));
const insideRings = (rs, x, y) => {
  let c = false;
  for (const ring of rs) for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
};

// Rivers that cross this region: the drawn path (clipped to the region on the page) and one label spot on the longest stretch inside.
function riversFor(regionId) {
  const rs = rings(map.regions[regionId].d);
  const byName = new Map();
  const minor = new Set();
  for (const r of riverData.rivers) { byName.set(r.name, [...(byName.get(r.name) ?? []), ...r.segs]); if (r.minor) minor.add(r.name); }
  const out = [];
  for (const [name, segs] of byName) {
    const runs = [];
    for (const seg of segs) {
      let run = [];
      for (let i = 0; i < seg.length - 1; i++) {
        const [x0, y0] = seg[i], [x1, y1] = seg[i + 1];
        const n = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / 2));
        for (let k = 0; k < n; k++) {
          const x = x0 + ((x1 - x0) * k) / n, y = y0 + ((y1 - y0) * k) / n;
          if (insideRings(rs, x, y)) run.push([x, y]); else if (run.length) { runs.push(run); run = []; }
        }
      }
      if (run.length) runs.push(run);
    }
    if (!runs.length) continue;
    const best = runs.sort((a, b) => b.length - a.length)[0];
    out.push({ name, minor: minor.has(name), d: segs.map((s) => 'M' + s.map((p) => p.join(',')).join('L')).join(''), len: best.length, xy: best[Math.floor(best.length / 2)] });
  }
  return out;
}

export function mapFeatures(regionId, regionCode, bbox, pad = 10) {
  const [x0, y0, x1, y1] = bbox;
  const inView = ([x, y]) => x >= x0 - pad && x <= x1 + pad && y >= y0 - pad && y <= y1 + pad;
  const ski = [];
  for (const s of spotsIn(regionId)) {
    if (s.activity !== 'ski') continue;
    const c = trusted(s.id);
    if (!c) continue;
    const xy = projectPoint(c.lon, c.lat);
    if (inView(xy)) ski.push({ id: s.id, name: shortName(s.name), full: s.name, xy, href: `/${regionId}/ski/#spot-${s.id}` });
  }
  const townPins = towns.filter((t) => t.region_code === regionCode).map((t) => ({ name: t.name, xy: projectPoint(t.lon, t.lat) })).filter((t) => inView(t.xy));
  const marks = landmarks.filter((l) => l.region_code === regionCode).map((l) => ({ name: l.name, xy: projectPoint(l.lon, l.lat) })).filter((l) => inView(l.xy));
  const rivers = riversFor(regionId).filter((r) => r.len >= 4 || r.minor);
  placeLabels(ski, marks, townPins, rivers, [x0 - pad, y0 - pad, x1 + pad, y1 + pad]);
  return { ski, towns: townPins, landmarks: marks, rivers };
}

// Greedy label placement, most important first: ski areas, parks, towns, rivers. Each label tries right, left, above, below
// and the diagonals; it is skipped (dot and tooltip remain) when every spot overlaps a dot or an earlier label.
function placeLabels(ski, marks, towns, rivers, [vx0, vy0, vx1, vy1]) {
  const dots = [...ski.map((p) => ({ xy: p.xy, r: 3.6 })), ...marks.map((m) => ({ xy: m.xy, r: 3.4 })), ...towns.map((t) => ({ xy: t.xy, r: 1.8 }))];
  const boxes = dots.map((d) => ({ x0: d.xy[0] - d.r, y0: d.xy[1] - d.r, x1: d.xy[0] + d.r, y1: d.xy[1] + d.r, own: d }));
  const hit = (a, b) => a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0;
  const place = (item, r, k, ownDot) => {
    const w = item.text.length * k, h = 5, [x, y] = item.xy, g = r + 1.2;
    const cands = [[g, 1.7, 'start', x + g, y - h / 2 - 0.3], [-g, 1.7, 'end', x - g - w, y - h / 2 - 0.3], [0, -g - 0.8, 'middle', x - w / 2, y - g - h],
      [0, g + 4.2, 'middle', x - w / 2, y + g], [g, -g, 'start', x + g, y - g - h + 1], [g, g + 3.5, 'start', x + g, y + g - 0.5],
      [-g, -g, 'end', x - g - w, y - g - h + 1], [-g, g + 3.5, 'end', x - g - w, y + g - 0.5]];
    for (const [dx, dy, anchor, bx, by] of cands) {
      const box = { x0: bx, y0: by, x1: bx + w, y1: by + h };
      if (box.x0 < vx0 || box.x1 > vx1 || box.y0 < vy0 || box.y1 > vy1) continue;
      if (boxes.some((b) => b.own !== ownDot && hit(box, b))) continue;
      boxes.push({ ...box, own: null });
      return { x: x + dx, y: y + dy, anchor };
    }
    return null;
  };
  const dotOf = (xy) => dots.find((d) => d.xy === xy);
  ski.forEach((p) => { p.label = place({ text: p.name, xy: p.xy }, 3.6, 2.7, dotOf(p.xy)); });
  marks.forEach((m) => { m.label = place({ text: m.name, xy: m.xy }, 3.4, 2.5, dotOf(m.xy)); });
  towns.forEach((t) => { t.label = place({ text: t.name, xy: t.xy }, 1.8, 2.25, dotOf(t.xy)); });
  rivers.filter((r) => !r.minor).forEach((r) => { r.label = place({ text: r.name, xy: r.xy }, 0.6, 2.1, {}); });
}

// Statewide map: every river once, unlabeled (labels collide with region names at that scale).
export function stateRivers() {
  const seen = new Map();
  for (const r of riverData.rivers) {
    const cur = seen.get(r.name) ?? { name: r.name, minor: !!r.minor, d: '' };
    cur.d += r.segs.map((sg) => 'M' + sg.map((q) => q.join(',')).join('L')).join('');
    seen.set(r.name, cur);
  }
  return [...seen.values()];
}
