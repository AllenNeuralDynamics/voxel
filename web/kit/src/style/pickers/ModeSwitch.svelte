<script lang="ts" module>
  import { Monitor, Moon, Sun } from '../../icons';
  import type { Mode } from '../theme.svelte';

  /** A menu trigger can show the icon of the current mode. */
  export const MODES: readonly { value: Mode; label: string; icon: typeof Sun }[] = [
    { value: 'light', label: 'Light', icon: Sun },
    { value: 'dark', label: 'Dark', icon: Moon },
    { value: 'auto', label: 'Auto', icon: Monitor }
  ];
</script>

<script lang="ts">
  import { RadioBar } from '../..';
  import { themes } from '../theme.svelte';

  /** Picks the light, dark or auto mode, as icons. In a menu, a pick keeps the menu open, so the change shows at once. */
  let { size = 'sm', class: className = 'w-full' }: { size?: 'xs' | 'sm'; class?: string } = $props();

  const prefs = $derived(themes.prefs.get());
</script>

<RadioBar
  aria-label="Mode"
  variant="soft"
  {size}
  class={className}
  options={MODES.map((mode) => mode.value)}
  value={prefs.mode}
  onChange={(mode) => themes.setMode(mode)}
  display={(value) => MODES.find((mode) => mode.value === value)?.icon ?? value}
/>
