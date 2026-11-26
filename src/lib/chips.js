// Status chips: short, activity-specific flags built from public forecast, snow, air and river data. Every chip is a fixed rule with a
// threshold below (my first judgment calls, meant to be edited) and carries its data in `why` (shown on hover). They are forecast-based:
// they are NOT a report from the resort, course or trail. At most 3 per row, most important first. Nothing is shown off season, except NWS alerts.
import { conditions } from './conditions.js';

export const T = {
  rainChance: 40,       // % chance of precipitation (today + tonight) for "Rain possible"
  wetCourse: 60,        // % for golf "Wet course"
  frostF: 32,           // forecast low (°F) tonight for golf "Frost delay possible"
  warmLowF: 25, warmHighF: 40,  // "Dress warm" if the low <= warmLowF or the high <= warmHighF (summer/shoulder-season activities)
  bitterF: 5,           // winter sports: "Bitter cold" if the low is at or below this
  windMph: 25,          // "Windy" at this sustained or gust speed
  heatF: 95,            // "Heat"
  aqiAmber: 101, aqiRed: 151,  // AirNow categories: Unhealthy for Sensitive Groups / Unhealthy
  newSnowIn: 2,         // SNOTEL 24 h depth change for "New snow!"
  niceHigh: [50, 85], niceRain: 20, niceWind: 15, // "Get outside!" window
};
const SNOW_ACTS = new Set(['ski', 'nordic', 'backcountry', 'snowmobile']);
const NO_ELEV = new Set(['golf', 'road-biking', 'fishing', 'paddle', 'hot-springs']); // elevation only matters in the label where it changes the weather story
const RIVER_ACTS = new Set(['whitewater', 'fishing', 'paddle']);

const mph = (s) => { const n = String(s ?? '').match(/\d+/g); return n ? Math.max(...n.map(Number)) : null; };
const gust = (t) => { const m = String(t ?? '').match(/gusts as high as (\d+) mph/i); return m ? Number(m[1]) : null; };

// The forecast point nearest in name to the spot's town (e.g. "McCall" for Brundage), else the region's main city.
// TODO: with spot coordinates switch the non-winter activities to the nearest point too.
function pointFor(spot, r) {
  const pts = r.forecast?.points ?? [];
  const town = (spot.town ?? '').toLowerCase();
  return pts.find((p) => p.name.toLowerCase().split(/\s*\/\s*/).some((n) => town.includes(n))) ?? pts[0] ?? null;
}
const shortName = (n) => n.replace(/\s*\(.*?\)/g, '').trim();
const ft = (n) => n.toLocaleString('en-US');

// The forecast a spot should show. Winter activities use the forecast at the spot's own coordinates (mountain elevation, from fetch_nws.py)
// when it exists; everything else, and winter spots without coordinates yet, use the nearest town's forecast.
const todayBoise = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Boise' }).format(new Date());
// Forecast days dated before today are dropped, so a stopped NWS fetch cannot show yesterday's forecast as "today".
const upcoming = (arr) => { const t = todayBoise(); const f = (arr ?? []).filter((d) => !d.date || d.date >= t); return f.length ? f : null; };
export function outlook(spot) {
  const r = conditions.regions[spot.region];
  if (!r) return null;
  let place, elev = null, days = null, periods = [], mountain = false;
  const gk = conditions.spotForecast?.bySpot?.[spot.id];  // forecast at the spot's own coordinates (any activity), when fetch_nws.py has one
  const g = gk && conditions.spotForecast.grids[gk];
  const gDays = upcoming(g?.days);
  if (gDays) {
    mountain = SNOW_ACTS.has(spot.activity);
    place = mountain ? shortName(spot.name) : (spot.town ?? '').split(/\s*[\/,]\s*/)[0] || shortName(spot.name);
    elev = NO_ELEV.has(spot.activity) ? null : g.elevationFt; days = gDays; periods = g.periods ?? [];
  } else {
    if (spot.activity === 'backcountry') return null;  // a zone or area has no point of its own: the region's town forecast says nothing about the terrain, so show none
    const p = pointFor(spot, r);
    if (!p) return null;
    place = p.name; days = upcoming(p.days); periods = p.periods ?? [];
  }
  if (days) {
    const d = days[0];
    return { town: place, elev, mountain, hi: d.hi, lo: d.lo, nextLo: days[1]?.lo ?? null, rain: d.precipChance, short: d.short ?? '', detail: d.detail ?? null, nightDetail: d.nightDetail ?? null,
      wind: Math.max(mph(d.wind) ?? 0, gust(d.detail) ?? 0, gust(d.nightDetail) ?? 0) || null, name: d.name };
  }
  if (!periods.length) return null;  // older data without the 7-day block: use the first four 12-hour periods
  const night = (x) => /night/i.test(x.name);
  const day = periods[0] && !night(periods[0]) ? periods[0] : null;
  const tonight = periods.find(night);
  return { town: place, elev, mountain, hi: day?.temp ?? null, lo: tonight?.temp ?? (day ? null : periods[0].temp), nextLo: null,
    rain: Math.max(...periods.slice(0, 2).map((x) => x.precipChance ?? 0)), short: periods[0].short ?? '', detail: null, nightDetail: null, wind: null, name: periods[0].name };
}

// One line for the verdict. Winter spots get the full written NWS forecast for the day (it names snow amounts, wind and gusts); others a short summary.
export function forecastLine(o, full = false) {
  if (!o) return null;
  const where = `${o.town}${o.elev ? ` (about ${ft(o.elev)} ft)` : ''}`;
  if (full && o.detail) return `${where} forecast: ${o.detail}${o.nightDetail && o.hi != null ? ` Tonight: ${o.nightDetail}` : ''}`;
  const t = o.hi != null ? `high ${o.hi}°${o.lo != null ? `, low ${o.lo}°` : ''}` : o.lo != null ? `low ${o.lo}° tonight` : '';
  return `${where} forecast: ${t}${t ? ', ' : ''}${o.short.toLowerCase()}${o.rain != null ? `, ${o.rain}% precip` : ''}.`;
}
export const isWinter = (a) => SNOW_ACTS.has(a);

function newSnow(spot, r) {
  const first = (spot.name ?? '').toLowerCase().split(/[\s/(]/)[0];
  const sts = (r.snow ?? []).filter((s) => s.depth?.status === 'fresh' && s.depthChange24h?.status === 'fresh' && s.depthChange24h.value !== null);
  const own = sts.filter((s) => first.length > 3 && (s.area ?? '').toLowerCase().includes(first));
  const pool = own.length ? own : sts;  // a station at the area itself first, else any station in the region
  return pool.filter((s) => s.depthChange24h.value >= T.newSnowIn).sort((a, b) => b.depthChange24h.value - a.depthChange24h.value)[0] ?? null;
}

export function chipsFor(spot, state, rd) {
  const r = conditions.regions[spot.region];
  if (!r) return [];
  const out = [];  // {text, cls, why, rank}
  const add = (rank, text, cls, why) => out.push({ rank, text, cls, why });
  const a = spot.activity, snowAct = SNOW_ACTS.has(a);
  const alert = (r.alerts ?? []).find((x) => x.countsTowardLevel); // alerts covering only a corner of the region stay on the hub and alert bar; without spot coordinates we can't tell which spots they touch
  if (alert) add(0, 'NWS alert', alert.level === 'red' ? 'red' : 'amber', `${alert.event} for part of this region (NWS)`);
  if (state === 'low') return out.slice(0, 1);
  const o = outlook(spot);
  const aq = (r.air?.points ?? []).filter((p) => p.aqi?.status === 'fresh' && p.aqi.value !== null).sort((x, y) => y.aqi.value - x.aqi.value)[0];
  if (aq && aq.aqi.value >= T.aqiAmber) add(1, 'Smoke', aq.aqi.value >= T.aqiRed ? 'red' : 'amber', `AQI ${aq.aqi.value} at ${aq.name} (AirNow)`);
  const wet = o && /rain|shower|drizzle|thunder/i.test(o.short);
  const snowy = o && /snow|flurr|blizzard|wintry/i.test(o.short);
  if (o) {
    if (o.wind != null && o.wind >= T.windMph) add(2, 'Windy', 'amber', `Wind up to ${o.wind} mph in the ${o.town} forecast (NWS)`);
    if (o.hi != null && o.hi >= T.heatF) add(2, 'Heat', 'amber', `High ${o.hi}°F in the ${o.town} forecast (NWS)`);
    if (snowAct) {
      if (o.lo != null && o.lo <= T.bitterF) add(2, 'Bitter cold', 'amber', `Low ${o.lo}°F in the ${o.town} forecast (NWS)`);
    } else if ((o.lo != null && o.lo <= T.warmLowF) || (o.hi != null && o.hi <= T.warmHighF)) {
      add(3, 'Dress warm', 'muted', `${o.hi != null ? `High ${o.hi}°F, ` : ''}low ${o.lo}°F in the ${o.town} forecast (NWS)`);
    }
    if (a === 'golf') {
      if (o.lo != null && o.lo <= T.frostF) add(2, 'Frost delay possible', 'amber', `Low ${o.lo}°F tonight in the ${o.town} forecast (NWS). Forecast-based, not a course report`);
      if (o.rain != null && o.rain >= T.wetCourse && wet) add(3, 'Wet course', 'muted', `${o.rain}% chance of precipitation in the ${o.town} forecast (NWS)`);
    }
    if (!snowAct && o.rain != null && o.rain >= T.rainChance && (wet || !snowy) && !(a === 'golf' && o.rain >= T.wetCourse && wet)) add(3, snowy ? 'Snow possible' : 'Rain possible', 'muted', `${o.rain}% chance of precipitation in the ${o.town} forecast (NWS)`);
    if (snowAct && snowy && o.rain != null && o.rain >= T.rainChance) add(4, 'Snow in forecast', 'muted', `${o.rain}% precip, ${o.short.toLowerCase()} in the ${o.town} forecast (NWS)`);
  }
  if (snowAct) {
    const ns = newSnow(spot, r);
    if (ns) add(3, 'New snow!', 'green', `+${ns.depthChange24h.value} in over 24 h at the ${ns.name} SNOTEL station (${ns.area})`);
  }
  if (RIVER_ACTS.has(a) && rd?.kind === 'flow' && rd.reading.status === 'fresh' && ['rising', 'falling'].includes(rd.trend)) add(3, rd.trend === 'rising' ? 'Rising' : 'Falling', 'muted', `${rd.label} is ${rd.trend} over the last few hours`);
  if (a === 'backcountry') add(5, 'Check avalanche forecast', 'amber', 'Backcountry travel: read the avalanche center forecast before you go');
  if (o && !snowAct && !alert && o.hi != null && o.hi >= T.niceHigh[0] && o.hi <= T.niceHigh[1] && (o.rain ?? 0) < T.niceRain && (o.wind ?? 0) < T.niceWind && !(aq && aq.aqi.value >= T.aqiAmber) && state === 'in') {
    add(6, 'Get outside!', 'green', `High ${o.hi}°F, ${o.rain ?? 0}% precip, light wind in the ${o.town} forecast (NWS)`);
  }
  if (!out.length && o) add(9, 'No weather flags', 'muted', `Checked the ${o.town} forecast for alerts, wind, heat, cold, rain, snow and smoke (NWS, AirNow): nothing notable`);
  return out.sort((x, y) => x.rank - y.rank).slice(0, 3);
}
