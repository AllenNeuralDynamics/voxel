<script lang="ts">
  import { Select } from 'bits-ui';

  import { ChevronDown } from '$lib/icons';
  import { Label } from '$lib/kit';
  import { type Density, type Mode, type ThemeId, themes } from '$lib/themes';

  const modes: Mode[] = ['light', 'dark', 'auto'];

  const densities: Density[] = ['compact', 'default', 'cozy'];

  const lightThemes = themes.list.filter((t) => t.swatches.light);
  const darkThemes = themes.list.filter((t) => t.swatches.dark);
  const lightItems = lightThemes.map((t) => ({ value: t.id, label: t.name }));
  const darkItems = darkThemes.map((t) => ({ value: t.id, label: t.name }));

  function getTheme(id: ThemeId) {
    return themes.list.find((t) => t.id === id);
  }

  function pillClass(selected: boolean): string {
    if (selected) return 'border-primary bg-primary/10 text-primary';
    return 'border-border text-fg-muted hover:border-fg/25 hover:text-fg';
  }

  const triggerClass =
    'flex h-ui-sm w-full min-w-0 items-center justify-between gap-2.5 rounded border border-input bg-transparent px-2.5 text-lg transition-colors hover:bg-element-hover focus:border-focused focus:outline-none';
  const itemClass =
    'flex w-full cursor-default items-center justify-between gap-2.5 rounded px-2.5 py-2 text-lg outline-none select-none data-highlighted:bg-element-hover data-highlighted:text-fg';
  const contentClass =
    'z-50 mt-1 w-(--bits-select-anchor-width) rounded border bg-floating p-1 shadow-md origin-(--bits-select-content-transform-origin) text-fg data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95';
</script>

{#snippet swatches(colors: readonly string[])}
  <div class="flex gap-0.5">
    {#each colors as color, i (i)}
      <span class="h-3 w-3 rounded-full border border-border/40" style="background: {color}"></span>
    {/each}
  </div>
{/snippet}

{#snippet themeSelect(variant: 'light' | 'dark')}
  {@const themeList = variant === 'light' ? lightThemes : darkThemes}
  {@const items = variant === 'light' ? lightItems : darkItems}
  {@const currentId = variant === 'light' ? themes.prefs.get().light : themes.prefs.get().dark}
  {@const setTheme = variant === 'light' ? themes.setLight.bind(themes) : themes.setDark.bind(themes)}
  <Select.Root type="single" value={currentId} onValueChange={(v) => v && setTheme(v as ThemeId)} {items}>
    <Select.Trigger id={`${variant}-theme`} aria-label={`${variant} theme`} class={triggerClass}>
      {@const t = getTheme(currentId)}
      <span class="min-w-0 truncate">{t?.name ?? 'Select...'}</span>
      <div class="flex shrink-0 items-center gap-2">
        {#if t?.swatches[variant]}
          {@render swatches(t.swatches[variant]!)}
        {/if}
        <ChevronDown class="shrink-0 opacity-50" width={12} height={12} />
      </div>
    </Select.Trigger>
    <Select.Portal>
      <Select.Content align="start" class={contentClass}>
        <Select.Viewport class="max-h-(--bits-select-content-available-height) overflow-y-auto">
          <Select.Group>
            {#each themeList as t (t.id)}
              <Select.Item value={t.id} label={t.name} class={itemClass}>
                <span class="min-w-0 truncate">{t.name}</span>
                <div class="flex shrink-0 items-center gap-2 pr-4">
                  {@render swatches(t.swatches[variant]!)}
                </div>
              </Select.Item>
            {/each}
          </Select.Group>
        </Select.Viewport>
      </Select.Content>
    </Select.Portal>
  </Select.Root>
{/snippet}

<div class="flex flex-col gap-6">
  <!-- Density -->
  <div class="flex items-center justify-between">
    <span class="text-lg font-medium text-fg">Density</span>
    <div class="flex gap-1">
      {#each densities as d (d)}
        <button
          class="h-ui-sm w-20 cursor-pointer rounded-md border px-2 text-base capitalize transition-colors hover:bg-element-hover {pillClass(
            themes.prefs.get().density === d
          )}"
          onclick={() => themes.setDensity(d)}
        >
          {d}
        </button>
      {/each}
    </div>
  </div>

  <!-- Mode -->
  <div class="flex items-center justify-between">
    <span class="text-lg font-medium text-fg">Mode</span>
    <div class="flex gap-1">
      {#each modes as m (m)}
        <button
          class="h-ui-sm w-20 cursor-pointer rounded-md border px-2 text-base capitalize transition-colors hover:bg-element-hover {pillClass(
            themes.prefs.get().mode === m
          )}"
          onclick={() => themes.setMode(m)}
        >
          {m}
        </button>
      {/each}
    </div>
  </div>

  <div class="flex items-center justify-between gap-2">
    <Label for="light-theme" class="text-lg font-medium text-fg">Light Theme</Label>
    <div class="w-62 min-w-0 shrink-0">
      {@render themeSelect('light')}
    </div>
  </div>

  <div class="flex items-center justify-between gap-2">
    <Label for="dark-theme" class="text-lg font-medium text-fg">Dark Theme</Label>
    <div class="w-62 min-w-0 shrink-0">
      {@render themeSelect('dark')}
    </div>
  </div>
</div>
