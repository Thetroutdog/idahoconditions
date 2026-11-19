// Loads conditions.json (real data from the fetchers) and falls back to the sample file so the site always builds.
import fs from 'node:fs';
import path from 'node:path';

const dir = path.resolve(process.cwd(), 'data');
const real = path.join(dir, 'conditions.json');
const file = fs.existsSync(real) ? real : path.join(dir, 'conditions.sample.json');
export const conditions = JSON.parse(fs.readFileSync(file, 'utf8'));
export const regionIds = Object.keys(conditions.regions);

const LEVEL_LABEL = { green: 'Clear', amber: 'Use caution', red: 'Hazards', gray: 'No current data' };
// Pass the region too: gray because only roads are missing reads "No alerts, roads not checked", not "No current data".
export const levelLabel = (l, r) => (l === 'gray' && r?.levelReasons?.[0]?.kind === 'roads-pending' ? 'No alerts, roads not checked' : LEVEL_LABEL[l] ?? 'No current data');

// Format a Reading's time in the region's own timezone, e.g. "Sun 11:30 AM MST".
export function fmtTime(iso, tz) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('en-US', {
    timeZone: tz, weekday: 'short', hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
  });
}
// Show a Reading: fresh value, or gray last-known with time when stale, or a dash when missing.
export function show(r, tz, digits) {
  if (!r || r.status === 'missing' || r.value === null) return { text: '—', cls: 'missing', note: 'no data' };
  const v = digits === undefined ? r.value : Number(r.value).toFixed(digits);
  const text = `${v} ${r.unit}`.trim();
  if (r.status === 'stale') return { text, cls: 'stale', note: `last reading ${fmtTime(r.observedAt, tz)}` };
  return { text, cls: 'fresh', note: r.provisional ? (r.source === 'AirNow' ? 'preliminary' : 'provisional') : '' };
}
