// Sitemap built from the same catalog the pages come from, so it cannot drift. No extra dependency.
import { regions, regionSlugs, activitySlugs, spotsFor, activityCounts } from '../lib/catalog.js';
const SITE = 'https://idahoconditions.com';
export function GET() {
  const paths = ['/', '/about/', '/whats-new/', '/terms/', '/privacy/', ...regionSlugs.map((r) => `/${r}/`), ...activitySlugs.filter((a) => spotsFor(a).length).map((a) => `/${a}/`),
    ...regions.flatMap((r) => Object.keys(activityCounts(r.id)).map((a) => `/${r.id}/${a}/`))];
  const body = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${paths.map((p) => `  <url><loc>${SITE}${p}</loc></url>`).join('\n')}\n</urlset>\n`;
  return new Response(body, { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
}
