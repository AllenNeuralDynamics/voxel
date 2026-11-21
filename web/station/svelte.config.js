import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    // A single-page app: every route falls back to index.html. Where the built files are served from is not decided
    // yet, so they go to the default build/ folder.
    adapter: adapter({ fallback: 'index.html' })
  }
};

export default config;
