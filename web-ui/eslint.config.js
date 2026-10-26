import { fileURLToPath } from 'node:url';

import { includeIgnoreFile } from '@eslint/compat';
import js from '@eslint/js';
import { defineConfig } from 'eslint/config';
import prettier from 'eslint-config-prettier';
import betterTailwind from 'eslint-plugin-better-tailwindcss';
import simpleImportSort from 'eslint-plugin-simple-import-sort';
import svelte from 'eslint-plugin-svelte';
import globals from 'globals';
import ts from 'typescript-eslint';

import svelteConfig from './svelte.config.js';

const gitignorePath = fileURLToPath(new URL('./.gitignore', import.meta.url));

const LIB_FOLDERS =
  'core|features|kit|shell|model|utils|themes|shortcuts|devices|imaging|issues|live|preview|run|stage';

/**
 * Import layers of `src/lib`, lowest first: core (failures, utils, model), kit, features, shell. A layer imports only
 * the layers below it. `allow` lists every `$lib` path the files may import; `deny` lists the paths they may not.
 */
function layer(files, { allow, deny = [] }) {
  const paths = (list) => list.map((path) => path.replaceAll('.', '\\.')).join('|');
  const patterns = [{ regex: `^(\\.\\./)+(${LIB_FOLDERS})(/|$)`, message: 'Import another lib folder through $lib.' }];
  if (allow) {
    const regex = allow.length ? `^\\$lib/(?!(${paths(allow)})(/|$))` : '^\\$lib/';
    patterns.push({ regex, message: `This layer imports only: ${allow.join(', ') || 'nothing in $lib'}.` });
  } else if (deny.length) {
    patterns.push({
      regex: `^\\$lib/(${paths(deny)})(/|$)`,
      message: `This layer does not import: ${deny.join(', ')}.`
    });
  }
  return { files, rules: { 'no-restricted-imports': ['error', { patterns }] } };
}

export default defineConfig(
  includeIgnoreFile(gitignorePath),
  {
    ignores: ['**/.old/**']
  },
  js.configs.recommended,
  ...ts.configs.recommended,
  ...svelte.configs.recommended,
  prettier,
  ...svelte.configs.prettier,
  {
    languageOptions: {
      globals: { ...globals.browser, ...globals.node }
    },
    plugins: {
      'simple-import-sort': simpleImportSort
    },
    rules: {
      // typescript-eslint strongly recommend that you do not use the no-undef lint rule on TypeScript projects.
      // see: https://typescript-eslint.io/troubleshooting/faqs/eslint/#i-get-errors-from-the-no-undef-rule-about-global-variables-not-being-defined-even-though-there-are-no-typescript-errors
      'no-undef': 'off',
      'simple-import-sort/imports': 'error',
      'simple-import-sort/exports': 'error',
      'no-restricted-properties': [
        'error',
        {
          object: 'toast',
          property: 'error',
          message: 'Use reportFailure from $lib/core/failures. It also adds the failure to the Issues list.'
        }
      ]
    }
  },
  {
    // The same check as `suggestCanonicalClasses` in the Tailwind CSS editor extension.
    files: ['src/**/*.{svelte,ts}'],
    plugins: { 'better-tailwindcss': betterTailwind },
    settings: { 'better-tailwindcss': { entryPoint: 'src/routes/layout.css', rootFontSize: 16 } },
    rules: { 'better-tailwindcss/enforce-canonical-classes': 'error' }
  },
  {
    // Shadows, blur and dashed edges belong to the frames in `roles.css` and to the kit, which defines the looks.
    files: ['src/**/*.{svelte,ts}'],
    ignores: ['src/lib/kit/**'],
    rules: {
      'better-tailwindcss/no-restricted-classes': [
        'error',
        {
          restrict: [
            {
              pattern: '^(.*:)?shadow(-.+)?$',
              message: 'Shadows belong to frames: use frame-raised, frame-floating, frame-dialog or frame-overlay.'
            },
            { pattern: '^(.*:)?backdrop-blur(-.+)?$', message: 'Blur belongs to frame-overlay.' },
            {
              pattern: '^(.*:)?border-dashed$',
              message: 'A dashed box is frame-placeholder, and a dashed button is the dashed Button variant.'
            }
          ]
        }
      ]
    }
  },
  {
    files: ['src/lib/features/issues/**'],
    rules: { 'no-restricted-properties': 'off' }
  },
  layer(['src/lib/core/**'], { allow: ['core'] }),
  layer(['src/lib/core/failures.ts'], { allow: [] }),
  layer(['src/lib/core/utils/**'], { allow: ['core/utils', 'core/failures'] }),
  layer(['src/lib/core/model/**'], { allow: ['core/model', 'core/utils', 'core/failures'] }),
  layer(['src/lib/kit/**'], {
    allow: ['kit', 'core/utils', 'core/failures', 'core/model/prop.svelte', 'core/model/device-rules']
  }),
  layer(['src/lib/navigation.ts'], { allow: ['core', 'kit/icons'] }),
  layer(['src/lib/features/**', 'src/lib/context.svelte.ts'], { deny: ['shell'] }),
  layer(['src/lib/shell/**'], {}),
  {
    files: ['**/*.svelte', '**/*.svelte.ts', '**/*.svelte.js'],
    languageOptions: {
      parserOptions: {
        projectService: true,
        extraFileExtensions: ['.svelte'],
        parser: ts.parser,
        svelteConfig
      }
    }
  }
);
