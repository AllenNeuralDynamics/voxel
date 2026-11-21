import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { loadEnv } from 'vite';
import { defineConfig } from 'vite-plus';

import { kitIcons } from '@voxel/kit/vite';

/** `exports` in the kit's package.json blocks deep imports by name, but a relative path skips it. */
const VIA_KIT = { regex: '^(\\.\\./)+kit(/|$)', message: 'Import the kit through @voxel/kit.' };
/** A relative import that climbs into another layer would skip the layer rules, so layers import each other via `$lib`. */
const VIA_LIB = { regex: '^(\\.\\./)+(core|features|shell)(/|$)', message: 'Import another layer through $lib.' };

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiTarget = env.VITE_API_URL || 'http://localhost:8000';

  const proxy: Record<string, object> = {
    '/api': { target: apiTarget, changeOrigin: true }
  };

  return {
    plugins: [tailwindcss(), kitIcons(), sveltekit()],
    optimizeDeps: { exclude: ['@bokuweb/zstd-wasm'] },
    server: { proxy },
    worker: { format: 'es' },
    lint: {
      ignorePatterns: ['static/**', '**/.old/**'],
      rules: {
        'no-restricted-imports': ['error', { patterns: [VIA_KIT] }],
        'no-restricted-properties': [
          'error',
          {
            object: 'toast',
            property: 'error',
            message: 'Use reportFailure from @voxel/kit/failures. It also adds the failure to the Issues list.'
          }
        ]
      },
      overrides: [
        { files: ['src/lib/features/issues/**'], rules: { 'no-restricted-properties': 'off' } },
        // The layers, lowest first: core, features, shell. A layer imports only the layers below it. An override
        // replaces the base rule, so each one repeats VIA_KIT.
        {
          files: ['src/lib/core/**'],
          rules: {
            'no-restricted-imports': [
              'error',
              {
                patterns: [
                  VIA_KIT,
                  VIA_LIB,
                  {
                    group: ['$lib/features', '$lib/features/**', '$lib/shell', '$lib/shell/**'],
                    message: 'Core imports only core.'
                  }
                ]
              }
            ]
          }
        },
        {
          files: ['src/lib/features/**', 'src/lib/context.svelte.ts'],
          rules: {
            'no-restricted-imports': [
              'error',
              {
                patterns: [
                  VIA_KIT,
                  VIA_LIB,
                  { group: ['$lib/shell', '$lib/shell/**'], message: 'Features do not import shell.' }
                ]
              }
            ]
          }
        },
        { files: ['src/lib/shell/**'], rules: { 'no-restricted-imports': ['error', { patterns: [VIA_KIT, VIA_LIB] }] } }
      ]
    }
  };
});
