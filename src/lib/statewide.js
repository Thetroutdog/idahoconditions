// Statewide rollups for the landing page. Counts come straight from live region data.
import { conditions, regionIds, fmtTime } from './conditions.js';
import { alertHref, alertGist, roadInfo, airDetail } from './regionview.js';
const R = () => regionIds.map((id) => conditions.regions[id]);

export function statewide() {
  const regs = R();
  const byId = new Map();
  for (const id of regionIds) for (const a of conditions.regions[id].alerts) {
    const e = byId.get(a.id) ?? { ...a, all: [], primary: [] };
    e.all.push(id); if (a.countsTowardLevel) e.primary.push(id);
    byId.set(a.id, e);
  }
  const rank = { red: 0, amber: 1 };
  const alerts = [...byId.values()].map((e) => {
    const ids = e.primary.length ? e.primary : e.all;
    return { ...e, regionId: ids[0], areas: ids.map((i) => conditions.regions[i].name).join(', '), href: alertHref(e, ids[0]), gistLine: alertGist(e) };
  }).sort((x, y) => (rank[x.level] ?? 2) - (rank[y.level] ?? 2));
  const aqs = regs.flatMap((r) => r.air.points.filter((p) => p.aqi?.status === 'fresh' && p.aqi.value !== null).map((p) => ({ name: p.name, v: p.aqi.value, cat: p.category, detail: airDetail(p), at: p.aqi.observedAt }))).sort((a, b) => b.v - a.v);
  const newest = (xs) => xs.filter(Boolean).sort().at(-1) ?? null;
  const times = { air: newest(aqs.map((a) => a.at)), fire: conditions.sources?.nifc?.fetchedAt ?? null, roads: newest(regs.map((r) => r.roads?.asOf)) };
  const fires = regs.flatMap((r) => r.fire.wildfires.filter((f) => f.status !== 'stale')).sort((a, b) => (b.acres ?? 0) - (a.acres ?? 0));
  const snow = regs.flatMap((r) => r.snow.filter((s) => s.depth?.status === 'fresh' && s.depth.value !== null).map((s) => ({ name: s.name, d: s.depth.value }))).sort((a, b) => b.d - a.d);
  const rivers = regs.flatMap((r) => r.rivers);
  const rivFresh = rivers.filter((g) => g.flow?.status === 'fresh' && g.flow.value !== null).length;
  const burns = regs.flatMap((r) => r.fire.prescribed.filter((f) => f.status !== 'stale'));
  const infos = regionIds.map((id) => ({ id, name: conditions.regions[id].name, ...roadInfo(conditions.regions[id]) }));
  const closures = infos.flatMap((i) => i.hwy.filter((c) => c.unplanned).map((c) => ({ name: c.name, desc: (c.description ?? '').replace(/\s+/g, ' ').trim().split(/\.\s/)[0].replace(/\.$/, ''), regionId: i.id, regionName: i.name })));
  const roads = { live: infos.some((i) => i.live), stale: infos.some((i) => i.stale), closures, planned: new Set(infos.flatMap((i) => i.hwy.filter((c) => !c.unplanned).map((c) => c.name))).size,
    winterRoads: new Set(infos.flatMap((i) => i.winter.map((w) => w.name))).size,  // a highway that crosses regions counts once
    passTotal: infos.reduce((n, i) => n + i.passes.length, 0), passMatched: infos.reduce((n, i) => n + i.passes.filter((p) => p.cond).length, 0),
    passBad: infos.reduce((n, i) => n + i.passes.filter((p) => p.cond && /closed|impass|ice|icy|slick|snow|pack|cover/i.test(p.cond)).length, 0) };
  const nws = { fresh: conditions.meta?.nwsFresh !== false, at: conditions.sources?.nws?.fetchedAt };
  // Items no region claims (build_conditions "unplaced"): shown inside the matching card as "Statewide <event>" with a one-line note.
  const up = conditions.unplaced ?? {};
  const unplaced = {
    weather: (up.weather ?? []).map((a) => ({ title: `Statewide ${a.event}`, ends: a.ends ?? null, desc: `Not tied to one region${a.ends ? `. Until ${fmtTime(a.ends, 'America/Boise')}` : ''}.${alertGist(a) ? ` ${alertGist(a)}` : ''}`, href: alertHref(a) })),
    roads: (up.roads ?? []).map((x) => ({ title: x.title, desc: x.desc ?? '', href: x.url })),
    air: (up.air ?? []).map((x) => ({ title: x.title, desc: x.desc ?? '', href: x.url })),
    fire: (up.fire ?? []).map((x) => ({ title: x.title, desc: x.desc ?? '', href: x.url })),
  };
  return { times, unplaced, alerts, aqs, fires, burns, snow, rivers: { total: rivers.length, fresh: rivFresh }, roads, nws };
}
