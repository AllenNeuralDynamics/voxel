<script lang="ts">
  import { SvelteSet } from 'svelte/reactivity';

  import { AUTO_COLORMAP } from '$lib/core/model';
  import { Button, DropdownMenu, NumberBox, Popover, TextBox } from '@voxel/kit';
  import { emissionToPreviewColor, isValidHex } from '@voxel/kit/colors';
  import { Check, ListFilter } from '@voxel/kit/icons';

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
  let hexInput = $state<HTMLInputElement | null>(null);
  let hiddenGroups = $state(new Set<string>());
  let searchInput = $state<HTMLInputElement | null>(null);

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

  function applyHex(text: string): void {
    const hex = text.trim();
    if (!channel.name || !isValidHex(hex)) return;
    previewer.setChannelColormap(channel.name, hex);
    open = false;
  }

  function updateAutoLevel(field: keyof AutoLevelsPreference, value: number): void {
    if (!channel.name) return;
    previewer.setChannelAutoLevels(channel.name, { ...channel.preferences.levels.auto, [field]: value });
  }

  function focusSearch(event: Event): void {
    event.preventDefault();
    searchInput?.focus();
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

      <Popover.Content
        class="flex w-auto flex-col-reverse"
        style="width: {columnWidth}px;"
        side="top"
        sideOffset={2}
        align="center"
        onOpenAutoFocus={focusSearch}
      >
        <div
          class="grid grid-cols-[2.75rem_minmax(0,1fr)_minmax(0,1fr)] items-center gap-1.5 border-t border-line-faint p-2 text-sm text-fg-muted"
        >
          <span>Black</span>
          <NumberBox
            value={channel.preferences.levels.auto.lowPercentile}
            onChange={(value) => updateAutoLevel('lowPercentile', value)}
            min={0}
            max={channel.preferences.levels.auto.highPercentile - 0.01}
            step={0.001}
            decimals={3}
            suffix="%"
            class="w-full"
          />
          <NumberBox
            value={channel.preferences.levels.auto.lowFloor}
            onChange={(value) => updateAutoLevel('lowFloor', value)}
            min={0}
            max={Math.min(dataTypeMax - 1, channel.preferences.levels.auto.highCeiling - 1)}
            step={1}
            home={0}
            decimals={0}
            prefix="≥"
            class="w-full"
          />

          <span>White</span>
          <NumberBox
            value={channel.preferences.levels.auto.highPercentile}
            onChange={(value) => updateAutoLevel('highPercentile', value)}
            min={channel.preferences.levels.auto.lowPercentile + 0.01}
            max={100}
            step={0.001}
            decimals={3}
            suffix="%"
            class="w-full"
          />
          <NumberBox
            value={channel.preferences.levels.auto.highCeiling}
            onChange={(value) => updateAutoLevel('highCeiling', value)}
            min={channel.preferences.levels.auto.lowFloor + 1}
            max={dataTypeMax}
            step={1}
            home={dataTypeMax}
            decimals={0}
            prefix="≤"
            class="w-full"
          />
        </div>

        <div class="flex items-center gap-1.5 p-2">
          <TextBox
            live
            bind:ref={searchInput}
            value={search}
            onChange={(text) => (search = text)}
            placeholder="Search colormaps..."
            class="min-w-0 flex-1"
          />
          <DropdownMenu.Root>
            <DropdownMenu.Trigger
              tabindex={-1}
              class="flex size-ui-sm shrink-0 items-center justify-center rounded border border-control-line bg-element-bg transition-colors hover:bg-element-hover {hasFilter
                ? 'text-fg'
                : 'text-fg-muted'}"
              aria-label="Filter groups"
            >
              <ListFilter width="14" height="14" />
            </DropdownMenu.Trigger>
            <DropdownMenu.Content class="z-60" side="top" sideOffset={4} align="end">
              {#each previewer.catalog as group (group.uid)}
                <DropdownMenu.CheckboxItem
                  closeOnSelect={false}
                  indicator={false}
                  checked={!hiddenGroups.has(group.uid)}
                  onCheckedChange={(checked) => {
                    const next = new SvelteSet(hiddenGroups);
                    if (checked) next.delete(group.uid);
                    else next.add(group.uid);
                    hiddenGroups = next;
                  }}
                  class="gap-1.5 px-1.5 py-1 text-xs text-fg-muted data-highlighted:bg-element-hover data-highlighted:text-fg"
                >
                  {#snippet children({ checked })}
                    <span class="inline-flex size-3 shrink-0 items-center justify-center">
                      {#if checked}<Check class="size-3  text-fg" />{/if}
                    </span>
                    <span>{group.label}</span>
                  {/snippet}
                </DropdownMenu.CheckboxItem>
              {/each}
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        </div>

        <div class="max-h-80 overflow-y-auto border-y border-line-faint px-2">
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

        <div class="p-2" style:--hex-color={triggerColor}>
          <TextBox
            bind:ref={hexInput}
            value=""
            onChange={applyHex}
            placeholder={triggerColor}
            aria-label="Custom hex color"
            class="border-l-[3px] border-l-(--hex-color) font-mono"
          >
            <!-- The box keeps the focus until the click. Leaving the box then sends the text. -->
            <Button
              variant="ghost"
              size="icon-sm"
              class="h-full rounded-none text-fg-muted"
              aria-label="Apply custom hex color"
              onmousedown={(event) => event.preventDefault()}
              onclick={() => hexInput?.blur()}
            >
              <Check width="14" height="14" />
            </Button>
          </TextBox>
        </div>
      </Popover.Content>
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
    background: var(--color-element-hover);
  }

  .swatch-row.selected {
    background: var(--color-element-hover);
    outline: 1px solid var(--color-line-selected);
  }

  .swatch-gradient {
    flex-shrink: 0;
    width: 2.9rem;
    height: 0.71rem;
    border-radius: 1px;
    border: 1px solid var(--line-faint);
  }

  .swatch-row:hover span,
  .swatch-row.selected span {
    color: var(--color-fg);
  }
</style>
