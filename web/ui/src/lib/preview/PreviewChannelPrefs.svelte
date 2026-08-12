<script lang="ts">
  import { DropdownMenu, Popover } from 'bits-ui';
  import { SvelteSet } from 'svelte/reactivity';

  import { emissionToPreviewColor, isValidHex } from '$lib/colors.svelte';
  import { Check, FilterVariant } from '$lib/icons';
  import { AUTO_COLORMAP } from '$lib/model';
  import { SpinBox } from '$lib/prop/numeric';

  import Histogram from './Histogram.svelte';
  import { colormapGradient, resolveColormapStops } from './render';
  import type { AutoLevelsPreference, PreviewChannel, PreviewSession } from './session.svelte';

  interface Props {
    previewer: PreviewSession;
    channel: PreviewChannel;
  }

  let { previewer, channel }: Props = $props();

  const label = $derived(channel.label ?? channel.config?.label ?? channel.name ?? '');
  const colormapPreference = $derived(channel.preferences.colormap);
  const autoColormap = $derived(emissionToPreviewColor(channel.config?.emission));
  const colormap = $derived(channel.resolvedColormap);
  const dataTypeMax = $derived(2 ** (channel.overviewFrame?.valid_bits ?? 16) - 1);
  const triggerColor = $derived(resolveColormapStops(colormap, previewer.catalog).at(-1) ?? '#ffffff');
  const colormapName = $derived(
    colormapPreference === AUTO_COLORMAP ? 'auto' : colormapPreference.startsWith('#') ? 'custom' : colormapPreference
  );
  const triggerGradient = $derived(colormapGradient(resolveColormapStops(colormap, previewer.catalog)));
  const autoGradient = $derived(colormapGradient(resolveColormapStops(autoColormap, previewer.catalog)));

  let open = $state(false);
  let search = $state('');
  let customHex = $state('');
  let hiddenGroups = $state(new Set<string>());
  let searchInput: HTMLInputElement;

  const hasFilter = $derived(hiddenGroups.size > 0);
  const searchResults = $derived.by(() => {
    const query = search.trim().toLowerCase();
    if (!query) return null;
    const results: { name: string; stops: string[] }[] = [];
    for (const group of previewer.catalog) {
      for (const [name, stops] of Object.entries(group.colormaps)) {
        if (name.toLowerCase().includes(query)) results.push({ name, stops });
      }
    }
    return results;
  });

  function pick(name: string): void {
    if (channel.name) previewer.setChannelColormap(channel.name, name);
    open = false;
  }

  function submitHex(): void {
    const hex = customHex.trim();
    if (!channel.name || !isValidHex(hex)) return;
    previewer.setChannelColormap(channel.name, hex);
    customHex = '';
    open = false;
  }

  function updateAutoLevel(field: keyof AutoLevelsPreference, value: number): void {
    if (!channel.name) return;
    previewer.setChannelAutoLevels(channel.name, { ...channel.preferences.levels.auto, [field]: value });
  }

  function focusSearch(event: Event): void {
    event.preventDefault();
    searchInput.focus();
  }
</script>

{#snippet swatch(value: string, name: string, gradient: string)}
  <button
    type="button"
    onclick={() => pick(value)}
    class="swatch-row {colormapPreference === value ? 'selected' : ''}"
    aria-label="Select colormap {name}"
  >
    <span class="swatch-gradient" style="background: {gradient}"></span>
    <span class="truncate text-xs text-fg-muted">{name}</span>
  </button>
{/snippet}

<Histogram
  {label}
  histData={channel.latestHistogram}
  levelsMin={channel.levelsMin}
  levelsMax={channel.levelsMax}
  onLevelsChange={(min, max) => {
    if (channel.name) previewer.setChannelLevels(channel.name, min, max);
  }}
  onAutoLevel={() => {
    if (channel.name) previewer.autoLevel(channel.name);
  }}
  {colormap}
  catalog={previewer.catalog}
  {dataTypeMax}
  visible={channel.visible}
  onVisibilityChange={(visible) => {
    if (channel.name) previewer.setChannelVisible(channel.name, visible);
  }}
>
  {#snippet centerControl(columnWidth: number)}
    <Popover.Root bind:open>
      <Popover.Trigger
        class="flex w-full cursor-pointer items-center gap-2 text-sm font-medium transition-[filter] hover:brightness-125"
        title="Colormap: {colormapName} · {label}"
        aria-label="Pick colormap for {label} (current: {colormapName})"
      >
        <span class="shrink-0 text-fg">{label}</span>
        <span class="h-2 min-w-0 flex-1 rounded-xs" style="background: {triggerGradient};"></span>
      </Popover.Trigger>

      <Popover.Portal>
        <Popover.Content
          class="z-50 flex flex-col-reverse rounded border border-border bg-surface shadow-xl outline-none"
          style="width: {columnWidth}px;"
          side="top"
          sideOffset={2}
          align="center"
          onOpenAutoFocus={focusSearch}
        >
          <div
            class="grid grid-cols-[2.75rem_minmax(0,1fr)_minmax(0,1fr)] items-center gap-x-1.5 gap-y-1.5 border-t border-border px-2 py-2 text-sm text-fg-muted"
          >
            <span>Black</span>
            <SpinBox
              model={{
                value: channel.preferences.levels.auto.lowPercentile,
                min: 0,
                max: channel.preferences.levels.auto.highPercentile - 0.01,
                step: 0.001,
                onChange: (value) => updateAutoLevel('lowPercentile', value)
              }}
              decimals={3}
              numCharacters={5}
              suffix="%"
              align="right"
              steppers={false}
              class="w-full"
            />
            <SpinBox
              model={{
                value: channel.preferences.levels.auto.lowFloor,
                min: 0,
                max: Math.min(dataTypeMax - 1, channel.preferences.levels.auto.highCeiling - 1),
                step: 1,
                home: 0,
                onChange: (value) => updateAutoLevel('lowFloor', value)
              }}
              decimals={0}
              numCharacters={5}
              prefix="≥"
              align="right"
              steppers={false}
              class="w-full"
            />

            <span>White</span>
            <SpinBox
              model={{
                value: channel.preferences.levels.auto.highPercentile,
                min: channel.preferences.levels.auto.lowPercentile + 0.01,
                max: 100,
                step: 0.001,
                onChange: (value) => updateAutoLevel('highPercentile', value)
              }}
              decimals={3}
              numCharacters={5}
              suffix="%"
              align="right"
              steppers={false}
              class="w-full"
            />
            <SpinBox
              model={{
                value: channel.preferences.levels.auto.highCeiling,
                min: channel.preferences.levels.auto.lowFloor + 1,
                max: dataTypeMax,
                step: 1,
                home: dataTypeMax,
                onChange: (value) => updateAutoLevel('highCeiling', value)
              }}
              decimals={0}
              numCharacters={5}
              prefix="≤"
              align="right"
              steppers={false}
              class="w-full"
            />
          </div>

          <div class="flex items-center gap-1.5 px-2 py-2">
            <input
              type="text"
              bind:this={searchInput}
              bind:value={search}
              placeholder="Search colormaps..."
              class="focus:border-focused h-6 min-w-0 flex-1 rounded border border-input bg-element-bg px-1.5 text-sm text-fg placeholder-fg-muted focus:outline-none"
            />
            <DropdownMenu.Root>
              <DropdownMenu.Trigger
                tabindex={-1}
                class="flex h-6 w-6 shrink-0 items-center justify-center rounded border border-input bg-element-bg transition-colors hover:bg-element-hover {hasFilter
                  ? 'text-fg'
                  : 'text-fg-muted'}"
                aria-label="Filter groups"
              >
                <FilterVariant width="14" height="14" />
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  class="z-60 min-w-32 rounded border border-border bg-surface p-1 shadow-xl outline-none"
                  side="top"
                  sideOffset={4}
                  align="end"
                >
                  {#each previewer.catalog as group (group.uid)}
                    <DropdownMenu.CheckboxItem
                      closeOnSelect={false}
                      checked={!hiddenGroups.has(group.uid)}
                      onCheckedChange={(checked) => {
                        const next = new SvelteSet(hiddenGroups);
                        if (checked) next.delete(group.uid);
                        else next.add(group.uid);
                        hiddenGroups = next;
                      }}
                      class="flex cursor-default items-center gap-1.5 rounded-sm px-1.5 py-1 text-xs text-fg-muted outline-none select-none data-highlighted:bg-element-hover data-highlighted:text-fg"
                    >
                      {#snippet children({ checked })}
                        <span class="inline-flex h-3 w-3 shrink-0 items-center justify-center">
                          {#if checked}<Check class="h-3 w-3 text-fg" />{/if}
                        </span>
                        <span>{group.label}</span>
                      {/snippet}
                    </DropdownMenu.CheckboxItem>
                  {/each}
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>

          <div class="max-h-80 overflow-y-auto border-y border-border px-2">
            <div class="swatch-grid py-2">
              {@render swatch(AUTO_COLORMAP, 'auto', autoGradient)}
            </div>
            {#if searchResults}
              {#if searchResults.length > 0}
                <div class="swatch-grid pb-2">
                  {#each searchResults as { name, stops } (name)}
                    {@render swatch(name, name, colormapGradient(stops))}
                  {/each}
                </div>
              {:else}
                <div class="pb-2 text-xs text-fg-muted">No matches</div>
              {/if}
            {:else}
              {#each previewer.catalog as group (group.uid)}
                {#if !hiddenGroups.has(group.uid)}
                  <div class="pt-1 pb-0.5 text-xs font-medium tracking-wide text-fg-muted uppercase">
                    {group.label}
                  </div>
                  <div class="swatch-grid pb-2">
                    {#each Object.entries(group.colormaps) as [name, stops] (name)}
                      {@render swatch(name, name, colormapGradient(stops))}
                    {/each}
                  </div>
                {/if}
              {/each}
            {/if}
          </div>

          <div class="flex items-center gap-1.5 px-2 py-2">
            <input
              type="text"
              bind:value={customHex}
              onkeydown={(event) => {
                if (event.key === 'Enter') submitHex();
              }}
              placeholder={triggerColor}
              size="5"
              class="focus:border-focused h-6 min-w-0 flex-1 rounded border border-l-[3px] border-input border-l-(--hex-color) bg-element-bg px-1.5 font-mono text-xs text-fg placeholder:text-fg-muted focus:outline-none"
              style:--hex-color={triggerColor}
            />
            <button
              type="button"
              onclick={submitHex}
              class="flex h-6 w-6 shrink-0 items-center justify-center rounded border border-input bg-element-bg text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
              aria-label="Apply custom hex color"
            >
              <Check width="14" height="14" />
            </button>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  {/snippet}
</Histogram>

<style>
  .swatch-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(6rem, 1fr));
    gap: 0.43rem 0.125rem;
  }

  .swatch-row {
    display: flex;
    align-items: center;
    gap: 0.43rem;
    padding: 0.14rem 0.25rem;
    border-radius: 2px;
    cursor: pointer;
    transition: background 0.15s;
    min-width: 0;
  }

  .swatch-row:hover {
    background: var(--color-accent);
  }

  .swatch-row.selected {
    background: var(--color-accent);
    outline: 1px solid var(--color-border);
  }

  .swatch-gradient {
    flex-shrink: 0;
    width: 2.9rem;
    height: 0.71rem;
    border-radius: 1px;
    border: 1px solid oklch(1 0 0 / 0.1);
  }

  .swatch-row:hover span,
  .swatch-row.selected span {
    color: var(--color-foreground);
  }
</style>
