import { defineConfig } from 'vite-plus';

export default defineConfig({
  fmt: {
    singleQuote: true,
    trailingComma: 'none',
    printWidth: 120,
    svelte: true,
    // Packages, then SvelteKit aliases, our workspace packages and icons, then relative files, like the old simple-import-sort order.
    sortImports: {
      internalPattern: ['$app/', '$env/', '$lib/', '@voxel/', '~icons/'],
      groups: ['side_effect', 'builtin', 'external', 'internal', ['parent', 'sibling', 'index'], 'unknown']
    },
    sortTailwindcss: { stylesheet: './station/src/routes/layout.css', functions: ['cn', 'tv'] },
    ignorePatterns: ['pnpm-lock.yaml']
  }
});
