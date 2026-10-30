<script lang="ts" module>
  import { Monitor, Moon, Sun } from '$lib/kit/icons';
  import type { Mode } from '$lib/kit/themes';

  /** The modes in the order the switch shows them. A menu trigger can show the icon of the current one. */
  export const MODES: readonly { value: Mode; label: string; icon: typeof Sun }[] = [
    { value: 'light', label: 'Light', icon: Sun },
    { value: 'dark', label: 'Dark', icon: Moon },
    { value: 'auto', label: 'Auto', icon: Monitor }
  ];
</script>

<script lang="ts">
  import { DropdownMenu } from '$lib/kit';
  import { themes } from '$lib/kit/themes';

  // Picks the mode inside a dropdown menu. A pick keeps the menu open, so the change shows at once.
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
