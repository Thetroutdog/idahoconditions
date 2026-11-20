// Starts the "Refresh and deploy" GitHub workflow. Runs on the cron trigger in wrangler.toml.
// No fetch handler on purpose: nothing on the internet can call this Worker.
const DISPATCH_URL = 'https://api.github.com/repos/Thetroutdog/idahoconditions/actions/workflows/refresh.yml/dispatches';

export async function dispatch(env, doFetch = fetch) {
  if (!env.GH_DISPATCH_TOKEN) {
    console.error('GH_DISPATCH_TOKEN is not set. Add it with: npx wrangler secret put GH_DISPATCH_TOKEN');
    throw new Error('missing GH_DISPATCH_TOKEN');
  }
  let res;
  try {
    res = await doFetch(DISPATCH_URL, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'idahoconditions-timer', // GitHub rejects requests without one
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ref: 'main' }),
    });
  } catch (e) {
    console.error('dispatch request failed:', String(e));
    throw e;
  }
  if (res.status === 204) {
    console.log('dispatch ok (204)');
    return;
  }
  // Anything else is a problem: 401 token expired or wrong, 403 missing Actions permission, 404 wrong repo or workflow, 422 bad ref.
  let detail = '';
  try { detail = (await res.text()).slice(0, 300); } catch { /* ignore */ }
  console.error(`dispatch FAILED: HTTP ${res.status} ${detail}`);
  throw new Error(`GitHub answered ${res.status}`);
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env));
  },
};
