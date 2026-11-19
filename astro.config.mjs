import { defineConfig } from 'astro/config';

// Static site; deployed to Cloudflare Pages by GitHub Actions.
export default defineConfig({
  site: 'https://idahoconditions.com',
  output: 'static',
});
