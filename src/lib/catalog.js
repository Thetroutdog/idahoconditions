// Spot catalog (data/spots.json, from Grok) plus season rules from docs/Idaho_Conditions_Build_Spec §4.
import fs from 'node:fs';
import path from 'node:path';
import { conditions } from './conditions.js';
import { chipsFor, outlook, forecastLine } from './chips.js';

const readJson = (f, fallback) => { try { return JSON.parse(fs.readFileSync(path.resolve(process.cwd(), 'data', f), 'utf8')); } catch { return fallback; } };
const cat = readJson('spots.json');
// data/spots_extra.json holds additions (golf, road biking, ...) in the same shape as spots.json, so Grok's seed file stays untouched.
const extra = readJson('spots_extra.json', { spots: [] });
// data/spot_links.json holds link edits per spot id: {"links": [...]} replaces, {"add": [...]} appends, {"remove": ["url fragment"]} drops.
const linkEdits = readJson('spot_links.json', {});
export const regions = cat.regions;                         // [{id, code, name, office}]
export const regionById = Object.fromEntries(regions.map((r) => [r.id, r]));
// Sites we never link to, whatever the catalog or link edits say (removed on purpose: the resort's own links are enough).
const BLOCKED_LINK_HOSTS = ['skiidaho.us'];
const applyLinks = (sp) => {
  const e = linkEdits[sp.id];
  let l = e?.links ? [...e.links] : [...sp.sources];
  if (e?.remove) l = l.filter((x) => !e.remove.some((f) => x.url.includes(f)));
  if (e?.add) l = [...l, ...e.add];
  l = l.filter((x) => !BLOCKED_LINK_HOSTS.some((h) => x.url.includes(h)));
  return { ...sp, sources: l };
};
export const spots = [...cat.spots, ...(extra.spots ?? [])].filter((s) => s.activity !== 'backpacking').map(applyLinks); // backpacking stays in the data, not the UI

// Fixed order for the landing "Browse by activity" row.
export const ACTIVITY_ORDER = ['ski', 'nordic', 'backcountry', 'snowmobile', 'whitewater', 'fishing', 'hike', 'mtb', 'road-biking', 'moto-bdr', 'hot-springs', 'climbing', 'paddle', 'golf'];
// Order used to sort tiles inside a season band on region hubs.
const HUB_ORDER = ['ski', 'nordic', 'backcountry', 'snowmobile', 'hot-springs', 'fishing', 'hike', 'mtb', 'road-biking', 'moto-bdr', 'whitewater', 'climbing', 'paddle', 'golf'];
const range = (a, b) => Array.from({ length: b - a + 1 }, (_, i) => a + i);
const IN_SEASON = {
  ski: [12, 1, 2, 3], nordic: [12, 1, 2, 3], backcountry: [12, 1, 2, 3, 4], snowmobile: [12, 1, 2, 3],
  'hot-springs': range(1, 12), fishing: range(1, 12),
  hike: range(4, 10), mtb: range(4, 10), 'road-biking': range(4, 10), golf: range(3, 11), 'moto-bdr': range(4, 10), whitewater: [4, 5, 6, 7], climbing: range(4, 10), paddle: range(5, 10),
};
const PRESEASON_NOV = ['ski', 'nordic', 'backcountry', 'snowmobile']; // November stays in the winter band

const byId = Object.fromEntries([...cat.activities, { id: 'road-biking', name: 'Road biking', catalog: 'Road Biking' }, { id: 'golf', name: 'Golf', catalog: 'Golf' }].map((a) => [a.id, a]));
export const activities = ACTIVITY_ORDER.map((id) => ({ ...byId[id], slug: id }));
export const activityBySlug = Object.fromEntries(activities.map((a) => [a.id, a]));
export const regionSlugs = regions.map((r) => r.id);
export const activitySlugs = ACTIVITY_ORDER;

const BOISE_NOW = new Date();
export const month = Number(BOISE_NOW.toLocaleString('en-US', { timeZone: 'America/Boise', month: 'numeric' }));
export const monthName = BOISE_NOW.toLocaleString('en-US', { timeZone: 'America/Boise', month: 'long' });

// 'in' | 'pre' | 'low'
export function seasonState(slug, m = month) {
  if (IN_SEASON[slug]?.includes(m)) return 'in';
  if (m === 11 && PRESEASON_NOV.includes(slug)) return 'pre';
  return 'low';
}
export const seasonLabel = { in: 'In season', pre: 'Preseason', low: 'Low season' };

export const spotsIn = (region, activity) => spots.filter((s) => s.region === region && (!activity || s.activity === activity));
export const spotsFor = (activity) => spots.filter((s) => s.activity === activity);
export function activityCounts(region) {
  const c = {};
  for (const s of spotsIn(region)) c[s.activity] = (c[s.activity] ?? 0) + 1;
  return c;
}
// Activities in a region, sorted per spec: season band first (in/pre, then low), then the hub order. Zero-spot activities omitted.
export function hubActivities(region) {
  const c = activityCounts(region);
  const list = HUB_ORDER.filter((a) => c[a]).map((a) => ({ ...activityBySlug[a], slug: a, count: c[a], state: seasonState(a) }));
  return [...list.filter((a) => a.state !== 'low'), ...list.filter((a) => a.state === 'low')];
}

// ---- Optional spot -> data source links (data/spot_sources.json). Only entries with confirmed:true are used. ----
// data/peaks.json: backcountry peaks. Their snow figures come from nearby SNOTEL stations (conditions.regions[r].peaks[spot id]), never from the peak itself.
const peakFacts = Object.fromEntries((readJson('peaks.json', { peaks: [] }).peaks ?? []).map((p) => [p.id, p]));
const nf = (n) => n.toLocaleString('en-US');
function peakView(spot, fl, o) {
  const pk = peakFacts[spot.id];
  const sts = conditions.regions[spot.region]?.peaks?.[spot.id] ?? [];
  if (!pk) return null;
  const parts = sts.map((s) => {
    const gap = s.feetBelowSummit, rel = gap >= 0 ? `${nf(gap)} ft below summit` : `${nf(-gap)} ft above summit`;
    const where = `Nearby station: ${s.name} SNOTEL, ${s.distanceMi} mi ${s.bearing}, ${rel}`;
    const d = s.depth;
    if (!d || d.value === null || d.status === 'missing') return `${where}. No current reading.`;
    return `${where}: ${d.value} in snow depth${d.status === 'stale' ? ' (reading delayed)' : ''}${s.swe?.value != null ? `, ${s.swe.value} in water equivalent` : ''}.`;
  });
  const first = sts[0]?.depth;
  const metric = first && first.value !== null && first.status !== 'missing'
    ? { text: `${first.value} ${first.unit}`, trend: `${sts[0].name}, ${sts[0].distanceMi} mi ${sts[0].bearing}`, observedAt: first.observedAt, stale: first.status === 'stale' } : null;
  let tail = '';
  if (o?.elev) { const gap = pk.elevationFt - o.elev; tail = ` The NWS forecast is for a point at about ${nf(o.elev)} ft${gap > 300 ? `, ${nf(gap)} ft below the summit` : ''}, not the summit.`; }
  const road = pk.highway ? ` Highway conditions: see Idaho 511 (${pk.highway}).` : '';
  const text = `${parts.join(' ')}${parts.length ? ' This is not a reading on the peak.' : 'No nearby station reading yet.'}${o?.mountain && fl ? ` ${fl}` : ''}${tail}${road}${pk.avalancheNote ? ` ${pk.avalancheNote}` : ''}`; // a region-level forecast point (valley town) is never shown for a peak: only the forecast at the peak's own coordinates
  return { metric, text, pill: { text: parts.length ? 'Nearby station' : 'Forecast only', cls: 'muted' } };
}

// data/snow_areas.json: ski and Nordic areas. Snow figures come from nearby SNOTEL stations (conditions.regions[r].areaStations[spot id]), never from the resort or trail system.
const areaFacts = Object.fromEntries((readJson('snow_areas.json', { areas: [] }).areas ?? []).map((a) => [a.id, a]));
const AREA_WORDS = {
  ski: { who: 'resort data', ref: 'mid-mountain', near: 'of mid-mountain', where: 'at the resort', tail: "Lifts, trails and opening dates: see the resort's own page." },
  nordic: { who: 'trail data', ref: 'this trail area', near: 'of this trail area', where: 'on the trails', tail: 'Grooming and trail status: see the trail system\'s own page.' },
};
function areaView(spot, fl, o) {
  const a = areaFacts[spot.id], w = AREA_WORDS[spot.activity];
  if (!a || !w) return null;
  const sts = conditions.regions[spot.region]?.areaStations?.[spot.id] ?? [];
  const about = spot.activity === 'ski' ? '' : 'about ';
  const parts = sts.map((s) => {
    const g = s.feetVsMid, r10 = (n) => nf(Math.round(n / 10) * 10);
    const rel = Math.abs(g) < 100 ? `about the same elevation as ${w.ref}` : g > 0 ? `${about}${r10(g)} ft above ${w.ref}` : `${about}${r10(-g)} ft below ${w.ref}`;
    const where = `${s.name} SNOTEL station, ${s.distanceMi} mi ${s.bearing} ${w.near}, ${rel}`;
    const d = s.depth;
    if (!d || d.value === null || d.status === 'missing') return `${where}: no current reading.`;
    const ch = s.depthChange24h;
    const chg = ch && ch.value !== null && ch.status !== 'missing' && !ch.suspect && ch.value !== 0 ? `, ${ch.value > 0 ? '+' : ''}${ch.value} in in 24 h` : '';
    return `${where}: ${d.value} in snow depth${chg}${d.status === 'stale' ? ' (reading delayed)' : ''}.`;
  });
  const first = sts[0]?.depth;
  const metric = first && first.value !== null && first.status !== 'missing'
    ? { text: `${first.value} ${first.unit}`, trend: `${sts[0].name}, ${sts[0].distanceMi} mi ${sts[0].bearing}`, observedAt: first.observedAt, stale: first.status === 'stale' } : null;
  const snow = parts.length ? `Nearby station, not ${w.who}. ${parts.join(' ')} It is not a reading ${w.where}, and snow can differ a lot with distance and elevation.` : 'No SNOTEL station close enough to represent this area.';
  let tail = '';
  if (o?.elev) { const gap = a.midFt - o.elev; tail = ` The NWS forecast is for a point at about ${nf(o.elev)} ft${Math.abs(gap) > 300 ? `, ${nf(Math.abs(gap))} ft ${gap > 0 ? 'below' : 'above'} ${w.ref}` : `, near ${w.ref}`}.`; }
  const text = `${snow}${o?.mountain && fl ? ` ${fl}` : ''}${tail} ${w.tail}`;
  return { metric, text, pill: { text: parts.length ? 'Nearby station' : 'Forecast only', cls: 'muted' } };
}

let sources = {};
try { sources = JSON.parse(fs.readFileSync(path.resolve(process.cwd(), 'data', 'spot_sources.json'), 'utf8')); } catch { /* optional */ }

export function readingFor(spot) {
  const src = sources[spot.id];
  if (!src || src.confirmed !== true) return null;
  const reg = conditions.regions[spot.region];
  if (src.usgs || src.noaa) {
    const gid = src.usgs ? `USGS-${src.usgs}` : `NOAA-${src.noaa.toUpperCase()}`;
    // The gauge may sit in a neighbouring region (e.g. Salmon at White Bird is a Clearwater gauge used by Main Salmon runs).
    const g = reg?.rivers.find((x) => x.id === gid) ?? Object.values(conditions.regions).flatMap((r) => r.rivers ?? []).find((x) => x.id === gid);
    if (g && g.flow && g.flow.status !== 'missing' && g.flow.value !== null) return { kind: 'flow', reading: g.flow, trend: g.trend, temp: g.waterTemp, label: src.usgs ? `${src.gauge || 'USGS'} (USGS ${src.usgs})` : `${src.gauge} (NOAA ${src.noaa.toUpperCase()})`, src };
  }
  if (src.snotel) {
    const s = reg?.snow.find((x) => x.id.startsWith(`${src.snotel}:`));
    if (s && s.depth && s.depth.status !== 'missing' && s.depth.value !== null) return { kind: 'depth', reading: s.depth, trend: null, label: `SNOTEL ${s.name}` };
  }
  return null;
}

// Flow word from a cited AW range (data/spot_sources.json). bands = [[upper cfs, label], ...] with null as the open top;
// range = [min, max]. Below the first bound reads "Below AW range". No range on file -> no word (never guessed).
export function flowWord(src, cfs) {
  if (!src || typeof cfs !== 'number') return null;
  if (src.bands) { for (const [hi, label] of src.bands) if (hi === null || cfs < hi) return label; }
  if (src.range) return cfs < src.range[0] ? 'Below AW range' : cfs > src.range[1] ? 'Above AW range' : 'In AW range';
  return null;
}

// ---- Templated verdicts: only readings, catalog facts and the calendar. No thresholds are guessed. ----
export function spotView(spot, tz) {
  const state = seasonState(spot.activity);
  const rd = readingFor(spot);
  const o = outlook(spot);
  const fl = forecastLine(o, true); // full written forecast for every activity
  let pill = { text: 'Check site', cls: 'muted' }, metric = null, verdict;
  if (rd) {
    const stale = rd.reading.status === 'stale';
    pill = stale ? { text: 'Reading delayed', cls: 'amber' } : { text: 'Live reading', cls: 'muted' };
    metric = { text: `${rd.reading.value} ${rd.reading.unit}`, trend: rd.trend && rd.trend !== 'unknown' ? rd.trend[0].toUpperCase() + rd.trend.slice(1) : '', observedAt: rd.reading.observedAt, label: rd.label, stale };
    const word = rd.kind === 'flow' && !stale ? flowWord(rd.src, rd.reading.value) : null;
    const tail = state === 'low' ? ` Off season in ${monthName}.` : '';
    verdict = `${word ? `${word}. ` : ''}${rd.label}: ${metric.text}${metric.trend ? `, ${metric.trend.toLowerCase()}` : ''}.${rd.temp && rd.temp.status === 'fresh' && rd.temp.value !== null ? ` Water ${Math.round(rd.temp.value)}°F.` : ''}${tail}${rd.src?.note ? ` ${rd.src.note}` : ''}${word && rd.src?.rangeSource ? ` Range: ${rd.src.rangeSource}.` : ''}`;
    if (word) pill = { text: word, cls: /Below|Above/.test(word) ? 'amber' : 'muted' };
    if (spot.activity !== 'whitewater' && fl) verdict = `${verdict} ${fl}`; // whitewater shows the gauge only; fishing and paddling add the forecast to flow and water temperature
  } else if (state === 'low') {
    pill = { text: 'Off season', cls: 'muted' };
    verdict = fl ?? `Off season in ${monthName}. Check the linked sources before planning.`;
  } else if (state === 'pre') {
    pill = { text: 'Preseason', cls: 'muted' };
    verdict = fl ?? (spot.activity === 'backcountry' ? 'Check the linked sources for additional information.' : 'Preseason. Check the linked sources for opening dates.');
  } else {
    if (fl) { pill = { text: 'Forecast only', cls: 'muted' }; verdict = fl; }
    else verdict = 'No live reading connected yet. Check the linked sources.';
  }
  if (spot.peak) {
    const pv = peakView(spot, fl, o);
    if (pv) { metric = pv.metric; verdict = pv.text; pill = pv.pill; }
  }
  if (spot.activity === 'ski' || spot.activity === 'nordic') {
    const sv = areaView(spot, fl, o);
    if (sv) { metric = sv.metric; verdict = sv.text; pill = sv.pill; }
  }
  const aw = sources[spot.id]?.confirmed === true && sources[spot.id].aw;
  const links = aw && !spot.sources.some((l) => l.url === aw) ? [...spot.sources, { label: 'AW river page', url: aw }] : spot.sources;
  if (!rd && sources[spot.id]?.confirmed === true && sources[spot.id].note && state !== 'low') verdict = `${verdict} ${sources[spot.id].note}`;
  // Golf lists many courses per town, so the full forecast sits behind a "Full forecast" toggle under a one-line summary.
  let more = null;
  if (spot.activity === 'golf' && fl) { more = fl; verdict = forecastLine(o, false); }
  return { ...spot, sources: links, pill, metric, verdict, more, chips: chipsFor(spot, state, rd) };
}

const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
export function seasonClause(slug) {
  const s = seasonState(slug);
  return s === 'low' ? `Off season in ${monthName}.` : s === 'pre' ? `Preseason in ${monthName}.` : 'In season.';
}
export function rollup(list, slug, extra = '') {
  const live = list.filter((s) => readingFor(s)).length;
  return `${plural(list.length, 'spot')}${extra}. ${seasonClause(slug)}${live ? ` ${live} with a live reading.` : ''}`;
}
export function tileSummary(slug, count) {
  const s = seasonState(slug);
  return s === 'low' ? `Off season in ${monthName}. Spots and links are still here.` : s === 'pre' ? 'Preseason. Opening dates come from each area.' : 'In season. Open the list for sources and links.';
}

const TITLES = { ski: 'ski areas', nordic: 'Nordic skiing', backcountry: 'backcountry skiing', snowmobile: 'snowmobiling', whitewater: 'whitewater', fishing: 'fishing', hike: 'hiking', mtb: 'mountain biking', 'road-biking': 'road biking', golf: 'golf', 'moto-bdr': 'moto and BDR riding', 'hot-springs': 'hot springs', climbing: 'climbing', paddle: 'paddling' };
export const activityTitle = (slug) => TITLES[slug] ?? slug;
export const spotNoun = (slug) => (slug === 'ski' ? 'areas' : 'spots');
