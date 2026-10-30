import { defineConfig } from 'vite-plus';

const LIB_FOLDERS =
  'core|features|kit|shell|model|utils|themes|shortcuts|devices|imaging|issues|live|preview|run|stage';

/**
 * Import layers of `src/lib`, lowest first: core (failures, utils, model), kit, features, shell. A layer imports only
 * the layers below it. `allow` lists every `$lib` path the files may import; `deny` lists the paths they may not.
 */
function layer(files: string[], { allow, deny = [] }: { allow?: string[]; deny?: string[] }) {
  // Oxlint regexes have no lookahead, so `allow` uses path groups with `!` exceptions.
  const paths = (list: string[]) => list.flatMap((path) => [`$lib/${path}`, `$lib/${path}/**`]);
  const patterns: object[] = [
    { regex: `^(\\.\\./)+(${LIB_FOLDERS})(/|$)`, message: 'Import another lib folder through $lib.' }
  ];
  if (allow) {
    const group = ['$lib/**', ...paths(allow).map((path) => `!${path}`)];
    patterns.push({ group, message: `This layer imports only: ${allow.join(', ') || 'nothing in $lib'}.` });
  } else if (deny.length) {
    patterns.push({ group: paths(deny), message: `This layer does not import: ${deny.join(', ')}.` });
  }
  return { files: files.map((path) => `station/${path}`), rules: { 'no-restricted-imports': ['error', { patterns }] } };
}

export default defineConfig({
  fmt: {
    singleQuote: true,
    trailingComma: 'none',
    printWidth: 120,
    svelte: true,
    // Packages, then SvelteKit aliases and icons, then relative files, like the old simple-import-sort order.
    sortImports: {
      internalPattern: ['$app/', '$env/', '$lib/', '~icons/'],
      groups: ['side_effect', 'builtin', 'external', 'internal', ['parent', 'sibling', 'index'], 'unknown']
    },
    sortTailwindcss: { stylesheet: './station/src/routes/layout.css', functions: ['cn', 'tv'] },
    ignorePatterns: ['station/static/**', 'pnpm-lock.yaml']
  },
  lint: {
    ignorePatterns: ['station/static/**', '**/.old/**'],
    rules: {
      'no-restricted-properties': [
        'error',
        {
          object: 'toast',
          property: 'error',
          message: 'Use reportFailure from $lib/core/failures. It also adds the failure to the Issues list.'
        }
      ]
    },
    overrides: [
      { files: ['station/src/lib/features/issues/**'], rules: { 'no-restricted-properties': 'off' } },
      layer(['src/lib/core/**'], { allow: ['core'] }),
      layer(['src/lib/core/failures.ts'], { allow: [] }),
      layer(['src/lib/core/utils/**'], { allow: ['core/utils', 'core/failures'] }),
      layer(['src/lib/core/model/**'], { allow: ['core/model', 'core/utils', 'core/failures'] }),
      layer(['src/lib/kit/**'], {
        allow: ['kit', 'core/utils', 'core/failures', 'core/model/prop.svelte', 'core/model/device-rules']
      }),
      layer(['src/lib/navigation.ts'], { allow: ['core', 'kit/icons'] }),
      layer(['src/lib/features/**', 'src/lib/context.svelte.ts'], { deny: ['shell'] }),
      layer(['src/lib/shell/**'], {})
    ]
  }
});
