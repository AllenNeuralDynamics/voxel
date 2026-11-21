import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite-plus';

import { kitIcons } from '@voxel/kit/vite';

/** `exports` in the kit's package.json blocks deep imports by name, but a relative path skips it. */
const VIA_KIT = { regex: '^(\\.\\./)+kit(/|$)', message: 'Import the kit through @voxel/kit.' };

export default defineConfig({
  plugins: [tailwindcss(), kitIcons(), sveltekit()],
  lint: {
    ignorePatterns: ['static/**'],
    rules: {
      'no-restricted-imports': ['error', { patterns: [VIA_KIT] }]
    }
  }
});
