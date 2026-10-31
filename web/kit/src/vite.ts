import { fileURLToPath } from 'node:url';

import Icons from 'unplugin-icons/vite';

/** The kit's folder, where its icon sets are installed. */
const KIT = fileURLToPath(new URL('..', import.meta.url));

/** Builds the kit's icons from the kit's own icon sets. Each app adds it to its Vite plugins. */
export function kitIcons() {
  return Icons({ compiler: 'svelte', collectionsNodeResolvePath: KIT });
}
