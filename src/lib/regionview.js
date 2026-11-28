// Helpers that turn a region's live data into the small cards on region pages and the landing page.
import { conditions, fmtTime, regionIds } from './conditions.js';
import { NOTES } from './site.js';
import map from '../data/idaho-map.json';
import points from '../../data/region_points.json';
import fireData from '../../data/fire_links.json';

export const IDAHO511 = 'https://511.idaho.gov/';
// Standing "More fire info" links: the region's national forest page first, then the statewide sources (data/fire_links.json).
export const forestFireLinks = (id) => fireData.regions[id] ?? [];
export const fireLinks = (id) => [...(fireData.regions[id] ?? []), ...fireData.statewide];

// Official AQI category colors from EPA's AQI Technical Assistance Document (required by the AirNow data guidelines). Do not retune.
const AQI_BANDS = [[50, '#00E400', '#000'], [100, '#FFFF00', '#000'], [150, '#FF7E00', '#000'], [200, '#FF0000', '#fff'], [300, '#8F3F97', '#fff'], [Infinity, '#7E0023', '#fff']];
export function aqiColors(v) { const b = AQI_BANDS.find(([max]) => v <= max); return { bg: b[1], fg: b[2] }; }

// Air quality forecast for one region (data from scripts/fetch_airnow_forecast.py, freshness already applied at build time). Returns null when
// there is nothing current to show. An Action Day is information only: it never changes a region's level, chips or alert bar.
const CAT_TOP = [50, 100, 150, 200, 300, 301];
export const ACTION_DAY_LABEL = 'Air quality action day';
export const ACTION_DAY_NOTE = 'The air agency expects poor air and asks people to cut back on emissions, such as wood burning and idling. This is a forecast, not a current reading.';
export function airForecastView(r, maxDays = 4) {
  const f = r.airForecast;
  if (!f?.areas?.length) return null;
  const tz = r.tz;
  const ymd = (d) => d.toLocaleDateString('en-CA', { timeZone: tz });
  const today = ymd(new Date());
  const diff = (iso) => Math.round((Date.parse(`${iso}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / 86400000);
  const label = (iso) => { const n = diff(iso); return n === 0 ? 'Today' : n === 1 ? 'Tomorrow' : new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' }); };
  const areas = f.areas.map((a) => ({
    name: a.name, actionDay: !!a.actionDay, discussion: a.discussion || '',
    days: a.days.filter((d) => diff(d.date) >= 0).slice(0, maxDays).map((d) => ({ ...d, label: label(d.date), short: diff(d.date) === 0 ? 'Today' : new Date(`${d.date}T12:00:00Z`).toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' }), ...aqiColors(CAT_TOP[(d.cat ?? 1) - 1] ?? 301) })),
  })).filter((a) => a.days.length);
  return areas.length ? { areas, source: f.source, url: f.url } : null;
}

// "PM2.5 · Pocatello Garrett and Gould": the pollutant and the monitor behind a current air reading (the monitor is skipped when it only repeats the city name).
export const airDetail = (p) => [p.pollutant, p.siteName && p.siteName !== p.name ? p.siteName : null].filter(Boolean).join(' · ');

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
  // Today's high / low from the 7-day days (a forecast, not a reading); falls back to the first NWS period.
  const p = r.forecast?.points?.[0];
  const d = p?.days?.[0];
  if (d && (d.hi != null || d.lo != null)) return d.hi != null ? `${d.hi}°${d.lo != null ? ` / ${d.lo}°` : ''}` : `low ${d.lo}°`;
  const q = p?.periods?.[0];
  return q ? `${q.temp}°` : '';
}
export function dotClass(level) { return ['green', 'amber', 'red'].includes(level) ? level : 'gray'; }

export function projectPoint(lon, lat) {
  const { lon0, lat1, k, s, pad } = map.proj;
  return [pad + (lon - lon0) * k * s, pad + (lat1 - lat) * s];
}

// Extra facts the NIFC record carries, as short phrases: cause, who protects it, discovery date, and (only when true) that it is long-running with no news.
// Nothing here is a guess about strategy: it is the feed's own fields and two date comparisons.
export function fireFacts(f, tz = 'America/Boise') {
  const day = (iso) => new Date(iso).toLocaleDateString('en-US', { timeZone: tz, month: 'short', day: 'numeric' });
  const age = (iso) => (Date.now() - Date.parse(iso)) / 86400000;
  const unit = fireData.units?.[f.unit];
  const out = [];
  if (f.cause === 'Natural' || f.cause === 'Human') out.push(`${f.cause} cause`);
  if (unit) out.push(unit.name);
  if (f.discoveredAt) out.push(`discovered ${day(f.discoveredAt)}`);
  if (f.oldRecord) out.push(`possibly an old record: no containment figure ${Math.round(age(f.discoveredAt) / 30)} months after discovery, so it may no longer be active. Check with the forest`);
  else if (f.containmentPct == null) out.push('no containment reported');
  if (f.modifiedAt) out.push(`updated ${day(f.modifiedAt)}`);
  return out.join(' · ');
}
// Links for one fire: the managing forest's fire page (by protecting-unit code) and a map pin.
export function fireLinksFor(f, skip = []) {  // skip: links the card already shows elsewhere (the region's standing forest link), so none appears twice
  const unit = fireData.units?.[f.unit];
  return [unit && !skip.some((l) => l.href === unit.href) ? { label: `${unit.name} fire info`, href: unit.href } : null, f.lat != null && f.lon != null ? { label: 'Map', href: `https://www.google.com/maps?q=${f.lat},${f.lon}` } : null].filter(Boolean);
}

// Snow facts shared by the region card, the homepage card and the chips. A 24 h change is only shown when it is recent (hourly data, a few hours old) and the
// station did not jump (a one-hour step over 6 in is a sensor glitch, flagged at fetch time). It is a depth change, which includes settling: never call it snowfall.
export const SNOW_RECENT_HOURS = 12;
export function snowGain(s) {
  const c = s?.depthChange24h;
  if (!c || c.status !== 'fresh' || c.value == null || c.suspect) return null;
  return (Date.now() - Date.parse(c.observedAt)) / 3600000 <= SNOW_RECENT_HOURS ? c.value : null;
}
export const signedIn = (n) => `${n > 0 ? '+' : n < 0 ? '\u2212' : ''}${Math.abs(n)}`;
export const snowFresh = (s) => s.depth?.status === 'fresh' && s.depth.value !== null;

// One named fire: "Swamp fire, 45 acres" plus containment when NIFC gives it.
export const fireLine = (f) => `${f.name} fire${f.oldRecord ? ' (possibly an old record)' : ''}${f.acres != null ? `, ${Math.round(f.acres).toLocaleString('en-US')} acres` : ''}${f.containmentPct != null ? `, ${f.containmentPct}% contained` : ''}`;

export function statusStrip(id) {
  const r = conditions.regions[id];
  const tz = r.tz;
  const pts = r.forecast.points.filter((p) => p.periods?.[0]);
  const nwsFresh = conditions.meta?.nwsFresh !== false;
  const alertCount = nwsFresh ? r.alerts.length : 0;
  // High / low for today from the 7-day days, so it reads as a forecast; falls back to the first NWS period when days are missing.
  const tempLine = (p) => { const d = p.days?.[0]; if (d && (d.hi != null || d.lo != null)) return d.hi != null ? `${p.name} ${d.hi}°${d.lo != null ? ` / ${d.lo}°` : ''}` : `${p.name} low ${d.lo}°`; return `${p.name} ${p.periods[0].temp}°`; };
  const hasDays = r.forecast.points.some((p) => p.days?.length);
  const weather = {
    title: 'Weather',
    lead: pts.length ? pts.slice(0, 2).map(tempLine).join(' · ') : 'No forecast',
    sub: !nwsFresh ? 'Weather alerts are out of date.' : alertCount ? '' : pts[0] ? `${pts[0].periods[0].short}.` : 'Forecast unavailable.',
    links: ((l) => (l.length ? l : null))([alertCount ? { href: alertHref(r.alerts[0], id), ends: r.alerts.every((x) => x.ends) ? [...r.alerts.map((x) => x.ends)].sort().at(-1) : null, label: `${r.alerts[0].event}${alertCount > 1 ? ` (+${alertCount - 1} more)` : ''}: NWS details` } : null, hasDays ? { href: '#forecast', label: 'Seven-day forecast', open: 'forecast' } : null].filter(Boolean)),
    src: `National Weather Service${r.forecast.updated ? ` · ${fmtTime(r.forecast.updated, tz)}` : ''}`,
  };
  const road = roadInfo(r);
  const nRoads = new Set(road.winter.map((w) => w.name)).size;
  // An unplanned closure leads. A planned one (a parade, a long construction closure) never outranks current snow or ice: it moves to the second line.
  const unplanned = road.hwy.filter((c) => c.unplanned);
  const planned = road.hwy.length - unplanned.length;
  const plannedNote = planned ? `${planned} planned closure${planned === 1 ? '' : 's'}${unplanned.length ? '' : ' (not an emergency)'}` : '';
  const roads = {
    title: 'Roads',
    lead: !road.live ? 'Not connected yet' : unplanned[0] ? `${unplanned[0].name} closed` : nRoads ? `${nRoads} road${nRoads === 1 ? '' : 's'} with snow or ice` : planned ? 'No unplanned closures' : 'No closures reported',
    sub: !road.live ? 'Road conditions arrive with the Idaho 511 connection.' : [unplanned.length > 1 ? `+${unplanned.length - 1} more highway closure${unplanned.length > 2 ? 's' : ''}` : '', plannedNote, road.stale ? 'Road data is out of date' : ''].filter(Boolean).join('. ') + (unplanned.length > 1 || plannedNote || road.stale ? '.' : ''),
    links: [{ href: '#roads', label: 'Details' }, { href: IDAHO511, label: 'Idaho 511' }],
    note: NOTES.roads,
    src: `Idaho 511${road.asOf ? ` · ${fmtTime(road.asOf, tz)}` : ''}`,
  };
  // Every monitored city in the region with a fresh reading, worst first. The card leads with the worst one and lists the rest below it.
  const aqAll = r.air.points.filter((p) => p.aqi?.value != null && p.aqi?.status === 'fresh').sort((a, b) => b.aqi.value - a.aqi.value);
  const aqLine = (p) => `${p.name} AQI ${p.aqi.value}${p.category ? ` ${p.category}` : ''}`;
  const aqNew = aqAll.map((p) => p.aqi.observedAt).filter(Boolean).sort().at(-1);
  const fireList = r.fire.wildfires.filter((f) => f.status !== 'stale').sort((a, b) => (b.acres ?? 0) - (a.acres ?? 0));
  const fires = fireList.length;
  const burns = r.fire.prescribed.filter((f) => f.status !== 'stale').length;
  const fire = {
    title: 'Air, fire & smoke',
    lead: aqAll.length ? aqLine(aqAll[0]) : 'No current air reading',
    detail: aqAll.length ? airDetail(aqAll[0]) : '',
    sub: `${aqAll.length > 1 ? aqAll.slice(1).map(aqLine).join('. ') + '. ' : ''}${fires ? `${fireList.slice(0, 2).map(fireLine).join('. ')}${fires > 2 ? ` (+${fires - 2} more)` : ''}` : 'No wildfires reported'}${burns ? `, ${burns} prescribed burn${burns === 1 ? '' : 's'}` : ''}.`,
    links: [{ href: '#air-quality', label: 'Air quality' }, { href: '#wildfires', label: 'Wildfires and burns' }],
    note: NOTES.fire,
    src: `AirNow${aqNew ? ` · ${fmtTime(aqNew, tz)}` : ''} · NIFC${conditions.sources?.nifc?.fetchedAt ? ` · ${fmtTime(conditions.sources.nifc.fetchedAt, tz)}` : ''}`,
  };
  const sts = r.snow.filter(snowFresh);
  const deep = [...sts].sort((a, b) => b.depth.value - a.depth.value)[0];
  const gains = sts.map((s) => ({ s, g: snowGain(s) })).filter((x) => x.g !== null).sort((a, b) => b.g - a.g);
  const top = gains[0] && gains[0].g >= 1 ? gains[0] : null;
  const lead1 = top ? top.s : deep;  // the station the card is about
  const sn = lead1;
  const snow = {
    title: 'Snow & avalanche',
    lead: top ? `${top.s.name} ${signedIn(top.g)} in in 24 h` : deep ? `${deep.name} ${deep.depth.value} in deep` : 'No fresh snow reading',
    sub: !deep ? 'SNOTEL stations in this region.' : [
      top ? `${top.s.depth.value} in deep` : gains.length ? 'No station gained 1 in or more in 24 h' : 'No recent 24 h change available',
      top && deep !== top.s ? `Deepest: ${deep.name} ${deep.depth.value} in` : '',
      lead1.pctOfMedian?.value != null ? `Water content ${lead1.pctOfMedian.value}% of median` : '',
      deep.depthChange24h?.suspect ? `${deep.name} jumped sharply, so its change is not shown` : '',
    ].filter(Boolean).join('. ') + '.',
    note: NOTES.avalanche,
    src: `NRCS SNOTEL${sn?.depth?.observedAt ? ` · ${fmtTime(sn.depth.observedAt, tz)}` : ''}${sn?.depth?.provisional ? ' · hourly, provisional' : ''}`,
    links: [id === 'southwest' ? { href: 'https://payetteavalanche.org/', label: 'Payette Avalanche Center' } : null, { href: 'https://avalanche.org/', label: 'avalanche.org' }].filter(Boolean),
  };
  return [weather, roads, fire, snow];
}

// The public NWS alerts page for Idaho. Never a point-forecast (MapClick) page: those often show no Special Weather Statement and never show an expired one.
export const ALERTS_PAGE = 'https://www.weather.gov/alerts';
// One plain line on what the alert says, so a generic outbound link is not the only copy: the first sentence of NWS's description, else its (all-caps) headline in sentence case.
export function alertGist(a, n = 150) {
  let t = String(a?.summary ?? '').replace(/\s+/g, ' ').trim();
  if (t) t = t.split(/(?<=[.!?])\s/)[0];
  else if (a?.gist) { const g = String(a.gist).trim(); t = g === g.toUpperCase() ? g.charAt(0) + g.slice(1).toLowerCase() : g; }
  return t.length <= n ? t : t.slice(0, n).replace(/\s+\S*$/, '') + '…';
}
export function alertLink(_regionId) {
  return ALERTS_PAGE;
}

// Link for one alert: the page the NWS fetcher stored if it is a real alert page, else the Idaho alerts page (also for older data that stored MapClick).
export function alertHref(a, _regionId) {
  return a?.url && /^https?:\/\//.test(a.url) && !a.url.includes('MapClick') ? a.url : ALERTS_PAGE;
}

// Region alert bar: very short items from the region's own level reasons ("Winter Weather Advisory", "US-95 closed").
// Green regions get a calm "No active alerts" bar; gray (stale or missing data) says so instead of implying all clear.
// Same four words as the map legend. Every page has a bar: region pages show their region, all other pages show the statewide one.
export const BAR_LABEL = { red: 'Hazards', amber: 'Caution', green: 'Clear', gray: 'No current data' };
// One short phrase per reason: drop the "until <time>" tail and the "(N segments)" count.
export const shortReason = (t) => String(t).split(/ until /)[0].replace(/\s*\(\d+ segments?\)/, '').replace(/\s+/g, ' ').trim();

// Statewide bar: the worst region level wins (red, then amber). Gray only when no region has current data.
export function statewideBar() {
  const regs = regionIds.map((id) => ({ id, ...conditions.regions[id] })).filter((r) => r.level);
  const by = (lv) => regs.filter((r) => r.level === lv);
  const why = (r) => `${r.name} (${shortReason(r.levelReasons?.[0]?.text ?? r.summary ?? '')})`;
  const worst = by('red').length ? 'red' : by('amber').length ? 'amber' : null;
  if (worst) {
    const flagged = [...by('red'), ...by('amber')];
    const shown = by(worst).slice(0, 2);
    return { level: worst, kicker: BAR_LABEL[worst], text: shown.map(why).join(', '), moreCount: flagged.length - shown.length, href: '/#regions' };
  }
  const gray = by('gray');
  if (!regs.length || gray.length === regs.length) return { level: 'gray', kicker: BAR_LABEL.gray, text: 'Some conditions data is out of date. Check weather.gov and 511.idaho.gov.', moreCount: 0, href: '/#snapshot' };
  const note = gray.length ? `; no current data for ${gray.length <= 2 ? gray.map((r) => r.name).join(' and ') : `${gray.length} regions`}` : '';
  return { level: 'green', kicker: BAR_LABEL.green, text: gray.length ? `Clear in ${regs.length - gray.length} regions${note}` : 'No active alerts in any region', moreCount: 0, href: null };
}

export function regionBar(id) {
  const r = conditions.regions[id];
  if (!r) return null;
  const short = shortReason;
  const seen = new Set();
  const items = [];
  for (const x of r.levelReasons ?? []) {
    const t = short(x.text);
    if (t && !seen.has(t)) { seen.add(t); items.push(t); }
  }
  const href = `/${id}/#alerts`;
  if (r.level === 'red' || r.level === 'amber') {
    const shown = items.slice(0, 3);
    return { level: r.level, kicker: BAR_LABEL[r.level], text: shown.join(' · '), moreCount: items.length - shown.length, href };
  }
  if (r.level === 'green') return { level: 'green', kicker: BAR_LABEL.green, text: 'No active alerts', moreCount: 0, href };
  return { level: 'gray', kicker: BAR_LABEL.gray, text: items[0] ?? 'Some conditions data is out of date', moreCount: 0, href };
}
