// Keeps search engines out until launch. At launch set PUBLIC_ALLOW_INDEX=true in the build environment.
export function GET() {
  const allow = import.meta.env.PUBLIC_ALLOW_INDEX === 'true';
  const body = allow
    ? 'User-agent: *\nAllow: /\nSitemap: https://idahoconditions.com/sitemap.xml\n'
    : 'User-agent: *\nDisallow: /\n';
  return new Response(body, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
