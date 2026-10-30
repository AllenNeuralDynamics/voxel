/**
 * Shadows, blur and dashed edges belong to the frames in `roles.css` and to the kit, which defines the looks. This
 * fails when a class outside `src/lib/kit/` uses one of them.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

const ROOT = join(import.meta.dirname, '..', 'src');
const SKIP = join(ROOT, 'lib', 'kit');

const RULES: { pattern: RegExp; message: string }[] = [
  {
    pattern: /^(.*:)?shadow(-.+)?$/,
    message: 'Shadows belong to frames: use frame-raised, frame-floating, frame-dialog or frame-overlay.'
  },
  { pattern: /^(.*:)?backdrop-blur(-.+)?$/, message: 'Blur belongs to frame-overlay.' },
  {
    pattern: /^(.*:)?border-dashed$/,
    message: 'A dashed box is frame-placeholder, and a dashed button is the dashed Button variant.'
  }
];

// Class lists sit in quotes or template strings; a class never holds these characters.
const TOKEN_SPLIT = /[\s'"`{}(),;<>=]+/;

function* files(dir: string): Generator<string> {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (path !== SKIP) yield* files(path);
    } else if (/\.(svelte|ts)$/.test(entry.name)) {
      yield path;
    }
  }
}

let failures = 0;
for (const path of files(ROOT)) {
  readFileSync(path, 'utf8')
    .split('\n')
    .forEach((line, index) => {
      if (/^\s*(\/\/|\*|\/\*)/.test(line)) return;
      for (const token of line.split(TOKEN_SPLIT)) {
        const rule = RULES.find(({ pattern }) => pattern.test(token));
        if (!rule) continue;
        failures += 1;
        console.error(`${relative(process.cwd(), path)}:${index + 1}: ${token}: ${rule.message}`);
      }
    });
}
if (failures) process.exit(1);
