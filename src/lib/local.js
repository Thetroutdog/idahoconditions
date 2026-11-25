// Local conditions: sources that belong to one region (or a few), shown as collapsed sections in a "Local conditions" slot.
// To add one: a fetcher that writes regions.<id>.local.<key>, a body component (mapped in components/LocalSection.astro), and one entry below.
// Shared fields every local source carries in conditions.json: title, verdict, tone ('green' | 'amber' | 'neutral'), summary, asOf, stale.
// Rules: a local source never changes the region's alert level; it dims when stale instead of erroring; order is fixed (below), not by severity.
import { conditions } from './conditions.js';

export const LOCAL_SOURCES = [
  {
    key: 'r2r',
    order: 10,
    regions: ['southwest'],
    activities: ['hike', 'mtb'], // activity pages that show it (open by default there)
    linkLabel: 'Foothills trails',
    staleLabel: 'last trail report',
  },
];

// "6:12 AM" for today (in the region's time zone), "Nov 20" for an older day.
export function asOfLabel(iso, tz) {
  if (!iso) return '';
  const d = new Date(iso);
  const day = (x) => x.toLocaleDateString('en-US', { timeZone: tz });
  return day(d) === day(new Date())
    ? d.toLocaleTimeString('en-US', { timeZone: tz, hour: 'numeric', minute: '2-digit' })
    : d.toLocaleDateString('en-US', { timeZone: tz, month: 'short', day: 'numeric' });
}

// The local sections for a region (and, on an activity page, only those tagged for that activity), in fixed order.
export function localFor(regionId, activity = null) {
  const r = conditions.regions[regionId];
  const tz = r?.tz;
  return LOCAL_SOURCES.filter((s) => s.regions.includes(regionId) && (!activity || s.activities.includes(activity)))
    .sort((a, b) => a.order - b.order)
    .map((s) => ({ ...s, item: r?.local?.[s.key], tz, domId: `local-${s.key}` }))
    .filter((s) => s.item && s.item.verdict)
    .map((s) => {
      const stale = !!s.item.stale;
      const when = asOfLabel(s.item.asOf, tz);
      return { ...s, chip: { label: stale ? 'Not current' : s.item.verdict, tone: stale ? 'gray' : s.item.tone || 'neutral' },
        glance: stale ? `${s.staleLabel ?? 'last report'} ${when}` : s.item.asOf ? `as of ${when}` : '' };
    });
}
