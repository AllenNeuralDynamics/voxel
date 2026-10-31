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
  import { DropdownMenu } from '../..';
  import { themes } from '../theme.svelte';

  // A pick keeps the menu open, so the change shows at once.
  const prefs = $derived(themes.prefs.get());
</script>

<DropdownMenu.RadioGroup
  value={prefs.mode}
  onValueChange={(mode) => themes.setMode(mode as Mode)}
  aria-label="Mode"
  class="grid grid-cols-3 gap-0.5"
>
  {#each MODES as mode (mode.value)}
    <DropdownMenu.RadioItem
      value={mode.value}
      closeOnSelect={false}
      aria-label={mode.label}
      title={mode.label}
      class="justify-center rounded-sm ps-0 pe-0 text-fg-muted data-[state=checked]:bg-element-selected data-[state=checked]:text-fg [&>span:first-child]:hidden"
    >
      <mode.icon />
    </DropdownMenu.RadioItem>
  {/each}
</DropdownMenu.RadioGroup>
