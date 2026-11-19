// Helpers that turn a region's live data into the small cards on region pages and the landing page.
import { conditions, fmtTime } from './conditions.js';
import map from '../data/idaho-map.json';
import points from '../../data/region_points.json';

export const IDAHO511 = 'https://511.idaho.gov/';

// Official AQI category colors from EPA's AQI Technical Assistance Document (required by the AirNow data guidelines). Do not retune.
const AQI_BANDS = [[50, '#00E400', '#000'], [100, '#FFFF00', '#000'], [150, '#FF7E00', '#000'], [200, '#FF0000', '#fff'], [300, '#8F3F97', '#fff'], [Infinity, '#7E0023', '#fff']];
export function aqiColors(v) { const b = AQI_BANDS.find(([max]) => v <= max); return { bg: b[1], fg: b[2] }; }

// Road facts for one region, shared by the status strip, the alerts section and the landing page.
// Highway closures are full closures on interstates/US/state routes (unplanned first); local roads are only counted.
export function roadInfo(r) {
  const rd = r.roads ?? {};
  const live = !!rd.status && rd.status !== 'missing';
  const all = rd.closures ?? [];
  const hwy = all.filter((c) => c.highway && c.fullClosure).sort((a, b) => Number(b.unplanned) - Number(a.unplanned) || String(b.updated).localeCompare(String(a.updated)));
  const groups = new Map();
  for (const w of rd.winter ?? []) {
    const k = `${w.name}|${w.condition}`;
    const g = groups.get(k) ?? { name: w.name, condition: w.condition, n: 0, weather: new Set(), special: new Set() };
    g.n += 1;
    [].concat(w.weather ?? []).filter(Boolean).forEach((x) => g.weather.add(x));
    [].concat(w.secondary ?? []).filter(Boolean).forEach((x) => g.special.add(x));
    groups.set(k, g);
  }
  const sev = (c) => (/closed|impass/i.test(c) ? 0 : /ice|icy|slick/i.test(c) ? 1 : /snow|pack|cover/i.test(c) ? 2 : 3);
  const winter = [...groups.values()].map((g) => ({ ...g, weather: [...g.weather], special: [...g.special] }))
    .sort((a, b) => sev(a.condition) - sev(b.condition) || a.name.localeCompare(b.name));
  // Mountain passes: Idaho 511 gives name, highway and elevation only. `cond` is the condition of the highway segment that names the pass (matched in build_conditions.py); null when there is no match.
  const passes = (rd.passes ?? []).map((p) => ({ name: p.name, highway: p.highway, elevationFt: p.elevationFt, cond: p.roadCondition?.condition ?? null }))
    .sort((a, b) => (a.cond ? sev(a.cond) : 9) - (b.cond ? sev(b.cond) : 9) || a.name.localeCompare(b.name));
  return { live, stale: rd.status === 'stale', hwy, local: all.length - hwy.length, winter, passes, asOf: rd.asOf };
}

export function regionTemp(r) {
  const p = r.forecast?.points?.[0]?.periods?.[0];
  return p ? `${p.temp}°` : '';
}
export function dotClass(level) { return ['green', 'amber', 'red'].includes(level) ? level : 'gray'; }

export function projectPoint(lon, lat) {
  const { lon0, lat1, k, s, pad } = map.proj;
  return [pad + (lon - lon0) * k * s, pad + (lat1 - lat) * s];
}

export function statusStrip(id) {
  const r = conditions.regions[id];
  const tz = r.tz;
  const pts = r.forecast.points.filter((p) => p.periods?.[0]);
  const nwsFresh = conditions.meta?.nwsFresh !== false;
  const alertCount = nwsFresh ? r.alerts.length : 0;
  const weather = {
    title: 'Weather',
    lead: pts.length ? pts.slice(0, 2).map((p) => `${p.name} ${p.periods[0].temp}°`).join(' · ') : 'No forecast',
    sub: !nwsFresh ? 'Weather alerts are out of date.' : alertCount ? '' : pts[0] ? `${pts[0].periods[0].short}.` : 'Forecast unavailable.',
    links: alertCount ? [{ href: alertHref(r.alerts[0], id), label: `${r.alerts[0].event}${alertCount > 1 ? ` (+${alertCount - 1} more)` : ''}: NWS details` }] : null,
    src: `National Weather Service${r.forecast.updated ? ` · ${fmtTime(r.forecast.updated, tz)}` : ''}`,
  };
  const road = roadInfo(r);
  const nRoads = new Set(road.winter.map((w) => w.name)).size;
  const roads = {
    title: 'Roads',
    lead: !road.live ? 'Not connected yet' : road.hwy[0] ? `${road.hwy[0].name} ${road.hwy[0].unplanned ? 'closed' : 'closure'}` : nRoads ? `${nRoads} road${nRoads === 1 ? '' : 's'} with snow or ice` : 'No closures reported',
    sub: !road.live ? 'Road conditions arrive with the Idaho 511 connection.' : road.hwy.length > 1 ? `+${road.hwy.length - 1} more highway closure${road.hwy.length > 2 ? 's' : ''}.` : road.stale ? 'Road data is out of date.' : '',
    links: [{ href: '#alerts', label: 'Details' }, { href: IDAHO511, label: 'Idaho 511' }],
    src: `Idaho 511${road.asOf ? ` · ${fmtTime(road.asOf, tz)}` : ''}`,
  };
  // Every monitored city in the region with a fresh reading, worst first. The card leads with the worst one and lists the rest below it.
  const aqAll = r.air.points.filter((p) => p.aqi?.value != null && p.aqi?.status === 'fresh').sort((a, b) => b.aqi.value - a.aqi.value);
  const aqLine = (p) => `${p.name} AQI ${p.aqi.value}${p.category ? ` ${p.category}` : ''}`;
  const fires = r.fire.wildfires.filter((f) => f.status !== 'stale').length;
  const burns = r.fire.prescribed.filter((f) => f.status !== 'stale').length;
  const fire = {
    title: 'Fire & smoke',
    lead: aqAll.length ? aqLine(aqAll[0]) : 'No current air reading',
    sub: `${aqAll.length > 1 ? aqAll.slice(1).map(aqLine).join('. ') + '. ' : ''}${fires ? `${fires} wildfire${fires === 1 ? '' : 's'} reported` : 'No wildfires reported'}${burns ? `, ${burns} prescribed burn${burns === 1 ? '' : 's'}` : ''}.`,
    links: [{ href: '#alerts', label: 'Air, wildfire and burn details' }],
    src: 'AirNow · NIFC',
  };
  const sn = r.snow.filter((s) => s.depth?.status === 'fresh' && s.depth.value !== null).sort((a, b) => b.depth.value - a.depth.value)[0];
  const snow = {
    title: 'Snow & avalanche',
    lead: sn ? `${sn.name} ${sn.depth.value} in` : 'No fresh snow reading',
    sub: sn?.pctOfMedian?.value != null ? `Water content ${sn.pctOfMedian.value}% of median.` : 'SNOTEL stations in this region.',
    src: 'NRCS SNOTEL',
    links: [id === 'southwest' ? { href: 'https://payetteavalanche.org/', label: 'Payette Avalanche Center' } : null, { href: 'https://avalanche.org/', label: 'avalanche.org' }].filter(Boolean),
  };
  return [weather, roads, fire, snow];
}

// Human-readable NWS page for a region's alerts: the point forecast page for the region's main city lists active hazards and links the full alert text.
export function alertLink(regionId) {
  const name = conditions.regions[regionId]?.name;
  const pt = points.points.find((p) => p.region === name && p.primary) ?? points.points.find((p) => p.region === name);
  return pt ? `https://forecast.weather.gov/MapClick.php?lat=${pt.lat}&lon=${pt.lon}` : 'https://alerts.weather.gov';
}

// Best link for one alert: the per-alert zone link the NWS fetcher stores, else the region's main-city page.
export function alertHref(a, regionId) {
  return a?.url && a.url.includes('MapClick') ? a.url : alertLink(regionId);
}

// Region alert bar: very short items from the region's own level reasons ("Winter Weather Advisory", "US-95 closed").
// Green regions get a calm "No active alerts" bar; gray (stale or missing data) says so instead of implying all clear.
export function regionBar(id) {
  const r = conditions.regions[id];
  if (!r) return null;
  const short = (t) => String(t).split(/ until |: /)[0].replace(/\s+/g, ' ').trim();
  const seen = new Set();
  const items = [];
  for (const x of r.levelReasons ?? []) {
    const t = short(x.text);
    if (t && !seen.has(t)) { seen.add(t); items.push(t); }
  }
  const href = `/${id}/#alerts`;
  if (r.level === 'red' || r.level === 'amber') {
    const shown = items.slice(0, 3);
    return { level: r.level, kicker: 'Alert', text: shown.join(' · '), moreCount: items.length - shown.length, href };
  }
  if (r.level === 'green') return { level: 'green', kicker: 'Clear', text: 'No active alerts', moreCount: 0, href };
  return { level: 'gray', kicker: 'Notice', text: items[0] ?? 'Some conditions data is out of date', moreCount: 0, href };
}
