// Sun times for a region's primary point, computed locally (NOAA solar formulas, no outside API).
// Flat-horizon estimates, good to about a minute; mountains and canyons lose the sun earlier.
import fs from 'node:fs';
import path from 'node:path';

const rad = (d) => (d * Math.PI) / 180;
const deg = (r) => (r * 180) / Math.PI;

let points = [];
try { points = JSON.parse(fs.readFileSync(path.resolve(process.cwd(), 'data', 'region_points.json'), 'utf8')).points ?? []; } catch { points = []; }

// Sun zenith angles: horizon with refraction, end of civil twilight (6 below), end of astronomical twilight (18 below).
const Z = { rise: 90.833, civil: 96, astro: 108 };

// Minutes after 00:00 UTC of the given UTC-midnight date at which the sun crosses `zenith`.
// rising=true gives the morning crossing, false the evening one; null when it never happens that day.
function crossing(dayUtc, lat, lon, zenith, rising) {
  const jd = dayUtc / 86400000 + 2440587.5 + 0.5 - lon / 360;          // near local solar noon
  const t = (jd - 2451545) / 36525;
  const l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360;
  const m = 357.52911 + t * (35999.05029 - 0.0001537 * t);
  const e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t);
  const c = Math.sin(rad(m)) * (1.914602 - t * (0.004817 + 0.000014 * t)) + Math.sin(rad(2 * m)) * (0.019993 - 0.000101 * t) + Math.sin(rad(3 * m)) * 0.000289;
  const trueLong = l0 + c;
  const omega = 125.04 - 1934.136 * t;
  const lambda = trueLong - 0.00569 - 0.00478 * Math.sin(rad(omega));
  const eps = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60 + 0.00256 * Math.cos(rad(omega));
  const decl = Math.asin(Math.sin(rad(eps)) * Math.sin(rad(lambda)));
  const y = Math.tan(rad(eps / 2)) ** 2;
  const eqTime = 4 * deg(y * Math.sin(2 * rad(l0)) - 2 * e * Math.sin(rad(m)) + 4 * e * y * Math.sin(rad(m)) * Math.cos(2 * rad(l0)) - 0.5 * y * y * Math.sin(4 * rad(l0)) - 1.25 * e * e * Math.sin(2 * rad(m)));
  const cosHa = Math.cos(rad(zenith)) / (Math.cos(rad(lat)) * Math.cos(decl)) - Math.tan(rad(lat)) * Math.tan(decl);
  if (cosHa > 1 || cosHa < -1) return null;
  const ha = deg(Math.acos(cosHa));
  return 720 - 4 * (lon + (rising ? ha : -ha)) - eqTime;
}

const fmt = (ms, tz) => new Date(ms).toLocaleTimeString('en-US', { timeZone: tz, hour: 'numeric', minute: '2-digit' });
const abbr = (ms, tz) => new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'short' }).formatToParts(new Date(ms)).find((p) => p.type === 'timeZoneName')?.value ?? '';

// regionName e.g. "Clearwater"; tz is the region's IANA zone. Returns null if the region has no point.
export function sunTimes(regionName, tz, now = new Date()) {
  const want = String(regionName).toLowerCase();
  const pts = points.filter((p) => p.region.toLowerCase() === want);
  const p = pts.find((x) => x.primary) ?? pts[0];
  if (!p) return null;
  const [yy, mm, dd] = new Intl.DateTimeFormat('en-CA', { timeZone: tz }).format(now).split('-').map(Number);
  const day = Date.UTC(yy, mm - 1, dd);
  const at = (z, rising) => { const min = crossing(day, p.lat, p.lon, z, rising); return min === null ? null : day + min * 60000; };
  const rise = at(Z.rise, true), set = at(Z.rise, false), dusk = at(Z.civil, false), dark = at(Z.astro, false);
  if (rise === null || set === null) return { near: p.name, none: true };   // polar day or night (does not happen in Idaho)
  return {
    near: p.name,
    tzAbbr: abbr(set, tz),
    sunrise: fmt(rise, tz),
    sunset: fmt(set, tz),
    dusk: dusk === null ? null : fmt(dusk, tz),
    fullDark: dark === null ? null : fmt(dark, tz),   // null = the sky never gets fully dark tonight
  };
}
