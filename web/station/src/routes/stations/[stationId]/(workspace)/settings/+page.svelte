<script lang="ts">
  import type { Snippet } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';

  import { page } from '$app/state';
  import { getColormaps, getMarks, useAppBar } from '$lib/context.svelte';
  import { Prefs } from '$lib/core/prefs';
  import type { MarkKey } from '$lib/features/stage/marks.svelte';
  import { Button, Checkbox, ColorPicker, Dialog, RadioBar, toast } from '@voxel/kit';
  import { ChevronRight, LayoutDashboard, RotateCcw } from '@voxel/kit/icons';
  import { layoutPrefs } from '@voxel/kit/pane';
  import type { PrefGroup } from '@voxel/kit/pref';
  import { ThemePicker } from '@voxel/kit/style';

  /**
   * The settings of this browser, in sections. A section is a band across the page: its name, then a box of rows; a
   * row is a label, then its control; a row of colors also has a reset while a color is the person's own. The app bar
   * has the resets of the page:
   * Reset layout, while a pane is moved, and Reset workspace, which asks which groups of saved things to reset and
   * can be undone from the message that follows.
   */
  useAppBar(() => ({
    crumbs: [{ label: 'Settings' }],
    // Reset layout comes before Reset workspace, so that one stays in its place when the other comes or goes.
    actions: [
      ...(layoutPrefs.changed
        ? [{ label: 'Reset layout', icon: LayoutDashboard, onclick: () => layoutPrefs.reset() }]
        : []),
      { label: 'Reset workspace…', icon: RotateCcw, onclick: ask }
    ]
  }));

  const marks = getMarks();
  const AXES: MarkKey[] = ['x', 'y', 'z'];
  const colormaps = getColormaps();
  const REGIONS: MarkKey[] = ['region1', 'region2', 'region3', 'region4'];
  // A row: its label, its control, then the place of its reset. Only a row of colors has one: the other controls
  // show all their choices. The same form as the rows of the kit's theme picker.
  const ROW = 'grid min-h-ui-lg grid-cols-[7rem_minmax(0,1fr)_1rem] items-center gap-3 py-1.5';
  const WIDE = 'w-full max-w-[52rem]';

  // The groups ticked in the Reset workspace dialog.
  let asking = $state(false);
  const picked = new SvelteSet<PrefGroup>();
  const ownColormaps = $derived(colormaps.all.filter((each) => each.own).length);
  const ownGroups = $derived(colormaps.groups.filter((group) => group.own).length);

  /** Opens the dialog with every changed group ticked, but not one whose reset deletes what the person made. */
  function ask(): void {
    picked.clear();
    for (const { group, deletes } of Prefs.GROUPS) {
      if (group.changed && !deletes) picked.add(group);
    }
    asking = true;
  }

  function resetWorkspace(): void {
    const groups = [...picked];
    const before = groups.map((group) => group.saved);
    for (const group of groups) group.reset();
    asking = false;
    toast('Workspace reset', {
      action: { label: 'Undo', onClick: () => groups.forEach((group, index) => (group.saved = before[index])) }
    });
  }
</script>

<!-- The reset at the end of a row, while a value of the row is the person's own. -->
{#snippet reset(changed: boolean, label: string, onclick: () => void)}
  {#if changed}
    <button
      type="button"
      class="cursor-pointer rounded-xs text-fg-muted outline-none hover:text-fg focus-visible:ring-2 focus-visible:ring-focus"
      title="Reset {label}"
      aria-label="Reset {label}"
      {onclick}
    >
      <RotateCcw class="size-3" aria-hidden="true" />
    </button>
  {/if}
{/snippet}

<!-- A color as a square that opens its picker. `letter` names it in the row, as X does for an axis. -->
{#snippet swatch(key: MarkKey, label: string, presets: string[] = [], letter = '')}
  {@const fromTheme = marks.themeColors[key] ?? '#000000'}
  {@const value = marks.picks[key] ?? fromTheme}
  <span class="flex items-center gap-1.5">
    {#if letter}<span class="text-fg-muted">{letter}</span>{/if}
    <ColorPicker {value} defaultColor={fromTheme} presetColors={presets} onChange={(next) => marks.pick(key, next)}>
      {#snippet trigger(props)}
        <button
          {...props}
          type="button"
          class="size-5 cursor-pointer rounded-sm border border-control-line outline-none hover:border-control-line-hover focus-visible:ring-2 focus-visible:ring-focus"
          style:background-color={value}
          aria-label="{label} color"
        ></button>
      {/snippet}
    </ColorPicker>
  </span>
{/snippet}

<!-- A row of colors: its label, its swatches, then 1 reset for those of them that are the person's own. -->
{#snippet colors(label: string, keys: MarkKey[], swatches: Snippet)}
  <div class={ROW}>
    <span class="text-base text-fg">{label}</span>
    <div class="flex items-center gap-3">{@render swatches()}</div>
    {@render reset(
      keys.some((key) => marks.picks[key]),
      `the ${label.toLowerCase()} colors`,
      () => keys.forEach((key) => marks.reset(key))
    )}
  </div>
{/snippet}

<!-- A section as a band across the page: its name, then a box of rows that fills the width. A row is a label, its
control, then its reset; the controls of all rows end on 1 edge. On a narrow page the name goes above the box. -->
{#snippet band(label: string, rows: Snippet)}
  <section class="grid gap-x-6 gap-y-1.5 @3xl:grid-cols-[11rem_minmax(0,1fr)]" aria-label={label}>
    <h2 class="px-2.5 text-sm text-fg-muted @3xl:mt-3 @3xl:px-0 @3xl:text-base @3xl:text-fg">{label}</h2>
    <div class="min-w-0 frame-raised px-2.5 py-1">{@render rows()}</div>
  </section>
{/snippet}

{#snippet appearance()}
  <ThemePicker themes="tiles" />
{/snippet}

{#snippet general()}
  <div class={ROW}>
    <span class="text-base text-fg">Distance</span>
    <RadioBar
      value={Prefs.spatialUnit.get()}
      options={Prefs.SPATIAL_UNITS}
      display={Prefs.spatialUnitLabel}
      onChange={(unit) => Prefs.spatialUnit.set(unit)}
      variant="soft"
      size="md"
      aria-label="Distance unit"
      class={WIDE}
    />
  </div>
{/snippet}

{#snippet axes()}
  {@render swatch('x', 'X axis', ['#d55e00', '#e69f00', '#cc79a7'], 'X')}
  {@render swatch('y', 'Y axis', ['#009e73', '#56b4e9', '#f0e442'], 'Y')}
  {@render swatch('z', 'Z axis', ['#0072b2', '#56b4e9', '#cc79a7'], 'Z')}
{/snippet}

{#snippet markers()}
  {@render swatch('markers', 'Markers', ['#e254d4', '#ffffff', '#f0e442', '#56b4e9'])}
{/snippet}

{#snippet regions()}
  {#each REGIONS as key, index (key)}
    {@render swatch(key, `Region ${index + 1}`)}
  {/each}
{/snippet}

{#snippet viewColors()}
  <div class="flex flex-col divide-y divide-line-faint">
    {@render colors('Axes', AXES, axes)}
    {@render colors('Markers', ['markers'], markers)}
    {@render colors('Regions', REGIONS, regions)}
    <div class={ROW}>
      <span class="text-base text-fg">Colormaps</span>
      <a
        class="flex items-center gap-1 justify-self-start text-base text-accent-fg underline-offset-2 hover:underline"
        href="/stations/{page.params.stationId}/settings/colormaps"
      >
        Manage
        <ChevronRight class="size-3.5" aria-hidden="true" />
      </a>
    </div>
  </div>
{/snippet}

<div class="px-inset @container h-full overflow-y-auto pb-4">
  <!-- A wide page has no section name above the first box, so it gets more room at the top. -->
  <div class="flex flex-col gap-6 pt-3 @3xl:pt-5">
    {@render band('Appearance', appearance)}
    {@render band('General', general)}
    {@render band('View colors', viewColors)}
  </div>
</div>

<Dialog.Root bind:open={asking}>
  <Dialog.Content size="sm" showCloseButton={false}>
    <Dialog.Header>
      <Dialog.Title>Reset workspace</Dialog.Title>
      <Dialog.Description>Profiles, tasks and all data on the station stay.</Dialog.Description>
    </Dialog.Header>
    <div class="flex flex-col gap-2.5">
      {#each Prefs.GROUPS as { group, label, deletes } (group.id)}
        <div class={['flex items-center gap-2.5', deletes && 'mt-1 border-t border-line-faint pt-3.5']}>
          <Checkbox
            size="md"
            aria-label={label}
            value={picked.has(group)}
            disabled={!group.changed}
            onChange={(on) => (on ? picked.add(group) : picked.delete(group))}
          />
          <span class={[!group.changed && 'text-fg-muted']}>{label}</span>
          {#if deletes && group.changed}
            <span class="text-sm text-fg-muted">
              {ownColormaps} colormap{ownColormaps === 1 ? '' : 's'}, {ownGroups} group{ownGroups === 1 ? '' : 's'}
            </span>
          {/if}
        </div>
      {/each}
    </div>
    <Dialog.Footer>
      <Button variant="secondary" onclick={() => (asking = false)}>Cancel</Button>
      <Button variant="danger" disabled={picked.size === 0} onclick={resetWorkspace}>Reset</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
