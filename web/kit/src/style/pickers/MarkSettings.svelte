<script lang="ts">
  import { Button, ColorPicker } from '../..';
  import { RotateCcw } from '../../icons';
  import { toHex } from '../colors';
  import { type MarkKey, themes, watchTheme } from '../theme.svelte';

  const rows: { key: MarkKey; label: string; token: string; presets: string[] }[] = [
    {
      key: 'stage',
      label: 'Stage marks',
      token: '--stage-mark',
      presets: ['#e254d4', '#ffffff', '#f0e442', '#56b4e9']
    },
    { key: 'x', label: 'X axis', token: '--axis-x', presets: ['#d55e00', '#e69f00', '#cc79a7'] },
    { key: 'y', label: 'Y axis', token: '--axis-y', presets: ['#009e73', '#56b4e9', '#f0e442'] },
    { key: 'z', label: 'Z axis', token: '--axis-z', presets: ['#0072b2', '#56b4e9', '#cc79a7'] }
  ];

  let defaults = $state<Record<MarkKey, string>>({ stage: '#e254d4', x: '#cc0000', y: '#007a00', z: '#0063b5' });
  const picked = $derived(themes.marks.get());

  // Picked colors sit on the body, so the root still holds the theme colors.
  watchTheme(() => {
    const styles = getComputedStyle(document.documentElement);
    defaults = Object.fromEntries(
      rows.map((row) => [row.key, toHex(styles.getPropertyValue(row.token).trim())])
    ) as Record<MarkKey, string>;
  });
</script>

<div class="flex flex-col gap-3">
  {#each rows as row (row.key)}
    <div class="grid grid-cols-[7rem_auto_minmax(0,1fr)] items-center gap-3">
      <span class="text-base font-normal text-fg">{row.label}</span>
      <ColorPicker
        value={picked[row.key] ?? defaults[row.key]}
        presetColors={[...new Set([defaults[row.key], ...row.presets])]}
        onChange={(color) => themes.setMark(row.key, color)}
        label="{row.label} color"
      />
      {#if picked[row.key]}
        <Button
          variant="quiet"
          size="xs"
          class="-ml-1 justify-self-start"
          title="Use the theme color"
          aria-label="Reset custom {row.label} color"
          onclick={() => themes.resetMark(row.key)}
        >
          Custom<RotateCcw class="size-3" />
        </Button>
      {:else}
        <span class="text-sm text-fg-muted">Theme</span>
      {/if}
    </div>
  {/each}
</div>
