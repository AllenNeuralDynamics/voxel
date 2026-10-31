<script lang="ts">
  import { Button, Label, RadioBar, Select } from '../..';
  import { RotateCcw } from '../../icons';
  import { displayName } from '../../utils/format';
  import { DEFAULT_DENSITY, DENSITIES, type Mode, type ThemeId, themes } from '../theme.svelte';

  const modes: Mode[] = ['light', 'dark', 'auto'];

  // The sizes show as numbers for now. 4 word labels do not fit this panel.
  const densities = DENSITIES.map((level) => level.size);

  const lightThemes = themes.list.filter((t) => t.swatches.light).map((t) => t.id);
  const darkThemes = themes.list.filter((t) => t.swatches.dark).map((t) => t.id);

  function getTheme(id: ThemeId) {
    return themes.list.find((t) => t.id === id);
  }
</script>

{#snippet themeSelect(variant: 'light' | 'dark')}
  <Select
    id={`${variant}-theme`}
    value={variant === 'light' ? themes.prefs.get().light : themes.prefs.get().dark}
    options={variant === 'light' ? lightThemes : darkThemes}
    formatLabel={(id) => getTheme(id)?.name ?? id}
    onChange={(id) => (variant === 'light' ? themes.setLight(id) : themes.setDark(id))}
    size="md"
  >
    {#snippet trailing(id)}
      <span class="flex gap-0.5">
        {#each getTheme(id)?.swatches[variant] ?? [] as color, i (i)}
          <span class="size-3 rounded-full border border-line-faint" style:background={color}></span>
        {/each}
      </span>
    {/snippet}
  </Select>
{/snippet}

<div class="flex flex-col gap-4">
  <div class="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-4">
    <span class="flex items-center gap-1 text-base font-normal text-fg">
      Density
      {#if themes.prefs.get().density !== DEFAULT_DENSITY}
        <Button
          variant="quiet"
          size="icon-sm"
          title="Reset to {DEFAULT_DENSITY}"
          aria-label="Reset density to {DEFAULT_DENSITY}"
          onclick={() => themes.setDensity(DEFAULT_DENSITY)}
        >
          <RotateCcw class="size-3" />
        </Button>
      {/if}
    </span>
    <RadioBar
      value={themes.prefs.get().density}
      options={densities}
      onChange={(density) => themes.setDensity(density)}
      size="md"
      aria-label="Density"
      class="w-full"
    />
  </div>

  <div class="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-4">
    <span class="text-base font-normal text-fg">Mode</span>
    <RadioBar
      value={themes.prefs.get().mode}
      options={modes}
      formatLabel={displayName}
      onChange={(mode) => themes.setMode(mode)}
      size="md"
      aria-label="Mode"
      class="w-full"
    />
  </div>

  <div class="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-4">
    <Label for="light-theme" class="text-base font-normal text-fg">Light Theme</Label>
    <div class="min-w-0">
      {@render themeSelect('light')}
    </div>
  </div>

  <div class="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-4">
    <Label for="dark-theme" class="text-base font-normal text-fg">Dark Theme</Label>
    <div class="min-w-0">
      {@render themeSelect('dark')}
    </div>
  </div>
</div>
