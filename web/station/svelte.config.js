import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    // A single-page app: every route falls back to index.html. The built files go into the Python package, next to
    // the station's web code, so that `vxl station start` serves them.
    adapter: adapter({
      pages: '../../src/vxl/web/station/static',
      assets: '../../src/vxl/web/station/static',
      fallback: 'index.html'
    })
  }
};

export default config;
