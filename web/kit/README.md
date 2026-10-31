# @voxel/kit

The shared Svelte UI kit of the Voxel web apps: controls, display and layout parts, the look (fonts, sizes, colors,
themes) and the icons. Apps import it only through the entry points that `exports` in `package.json` lists:

```ts
import { Button, toast } from '@voxel/kit';
import { reportFailure } from '@voxel/kit/failures';
import { Check } from '@voxel/kit/icons';
// Fails: the kit does not export its folders.
import Button from '@voxel/kit/src/controls/Button.svelte';
```

An app sets it up in 2 files. Its main CSS file:

```css
@import 'tailwindcss';
@import '@voxel/kit/style.css';

/* Tailwind scans the kit's files too. The path is relative to this CSS file. */
@source '../../../kit/src';
```

Its `vite.config.ts`, so the kit's icons build:

```ts
import { kitIcons } from '@voxel/kit/vite';

export default defineConfig({
  plugins: [tailwindcss(), kitIcons(), sveltekit()]
});
```
