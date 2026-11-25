<script lang="ts">
  import { SvelteSet } from 'svelte/reactivity';

  import { page } from '$app/state';
  import { getColormaps, useAppBar } from '$lib/context.svelte';
  import { Prefs } from '$lib/core/prefs';
  import { type ColormapGroup, Colormaps } from '$lib/features/preview/colormaps.svelte';
  import { Button, ColorPicker, Popover, Section, TextBox } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { ChevronDown, Eye, EyeOff, GripVertical, Minus, Plus, RotateCcw, Trash } from '@voxel/kit/icons';
  import Sortable from '@voxel/kit/sortable';

  /**
   * The colormap groups of this browser: 1 row for each group, to drag into order, to hide and to open. An open group
   * shows its colormaps as rows of colors and name, takes a new label and more colormaps, and loses colormaps. A group of the person's
   * can be deleted, and a default group that changed can be reset. A colormap takes a new name in its row, and new
   * colors in the menu of its colors. The person's colormaps in no group follow, and only there is one deleted. The
   * app bar makes a group, and resets the default colormaps and groups while one of them is changed.
   */
  useAppBar(() => ({
    crumbs: [{ label: 'Settings', href: `/stations/${page.params.stationId}/settings` }, { label: 'Colormaps' }],
    actions: [
      ...(Prefs.colormaps.changed
        ? [{ label: 'Reset defaults', icon: RotateCcw, onclick: () => Prefs.colormaps.reset() }]
        : []),
      { label: 'New group', icon: Plus, onclick: addGroup }
    ]
  }));

  const colormaps = getColormaps();
  const open = new SvelteSet<string>();
  // The group whose list of colormaps to add is open, with the text of its search.
  let adding = $state<string | null>(null);
  let search = $state('');
  // The tile whose menu is open: its group, or null for a colormap in no group, then its id.
  let editing = $state<string | null>(null);

  // The rows of a group, in as many columns as fit. A column holds the colors and the longest name.
  const rows = 'grid grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] gap-x-5 gap-y-1.5';
  // A group's header and its rows have the same first column, for the grip and for the line under it.
  const rail = 'grid-cols-[1.75rem_minmax(0,1fr)]';

  /** The colormaps that `group` does not have and whose name matches the search. */
  function toAdd(group: ColormapGroup) {
    const query = search.trim().toLowerCase();
    return colormaps.all.filter((each) => !group.ids.includes(each.id) && each.name.toLowerCase().includes(query));
  }

  /** Makes a colormap of 1 color with a name that no colormap has, in `group`. */
  function create(group: string): void {
    const names = new Set(colormaps.all.map((each) => each.name));
    let count = 1;
    while (names.has(`colormap-${count}`)) count++;
    colormaps.addTo(group, colormaps.create(`colormap-${count}`, ['#ffffff']));
    adding = null;
  }

  function addGroup(): void {
    open.add(colormaps.addGroup('New group'));
  }
</script>

<!-- A colormap as a row: its colors, then its name as a box. The colors open a menu: the colors of the colormap, its
place in the group, the reset of a default colormap that changed, and, in no group, the delete of the colormap. -->
{#snippet row(id: string, group: ColormapGroup | null)}
  {@const colormap = colormaps.get(id)}
  {#if colormap}
    {@const key = JSON.stringify([group?.id ?? null, id])}
    {@const stops = colormap.stops}
    <div class="flex min-w-0 items-center gap-2 text-sm">
      <Popover.Root open={editing === key} onOpenChange={(now) => (editing = now ? key : null)}>
        <Popover.Trigger>
          {#snippet child({ props })}
            <button
              {...props}
              type="button"
              class="h-4 w-14 shrink-0 cursor-pointer rounded-xs border border-line-faint outline-none hover:border-control-line-hover focus-visible:ring-2 focus-visible:ring-focus"
              style:background={colormaps.gradient(id)}
              aria-label="Change {colormap.name}"
            ></button>
          {/snippet}
        </Popover.Trigger>
        <Popover.Content class="flex w-auto flex-col gap-2 p-2" side="bottom" align="start" sideOffset={4}>
          <div class="flex items-center gap-1.5">
            {#each stops as stop, index (index)}
              <ColorPicker
                value={stop}
                defaultColor={colormap.own ? undefined : Colormaps.DEFAULTS[id]?.[index]}
                label="Color {index + 1} of {colormap.name}"
                onChange={(color) => colormaps.setStops(id, stops.with(index, color))}
              />
            {/each}
            <Button
              variant="ghost"
              size="xs"
              aria-label="Add a color to {colormap.name}"
              disabled={stops.length >= 8}
              onclick={() => colormaps.setStops(id, [...stops, stops[stops.length - 1]])}
            >
              <Plus class="size-3.5" aria-hidden="true" />
            </Button>
            <Button
              variant="ghost"
              size="xs"
              aria-label="Remove the last color of {colormap.name}"
              disabled={stops.length <= 1}
              onclick={() => colormaps.setStops(id, stops.slice(0, -1))}
            >
              <Minus class="size-3.5" aria-hidden="true" />
            </Button>
          </div>
          <div class="flex items-center gap-2">
            {#if group}
              <Button
                variant="outline"
                size="xs"
                onclick={() => {
                  editing = null;
                  colormaps.removeFrom(group.id, id);
                }}
              >
                Remove from group
              </Button>
            {:else}
              <Button
                variant="outline"
                size="xs"
                onclick={() => {
                  editing = null;
                  colormaps.remove(id);
                }}
              >
                <Trash class="size-3.5" aria-hidden="true" />
                Delete colormap
              </Button>
            {/if}
            {#if colormap.changed}
              <Button variant="outline" size="xs" onclick={() => colormaps.reset(id)}>
                <RotateCcw class="size-3.5" aria-hidden="true" />
                Reset
              </Button>
            {/if}
          </div>
        </Popover.Content>
      </Popover.Root>
      <TextBox
        size="inline"
        class="min-w-0"
        value={colormap.name}
        aria-label="Name of {colormap.name}"
        onChange={(text) => colormaps.setName(id, text.trim())}
      />
    </div>
  {/if}
{/snippet}

<div class="h-full page-body pt-3">
  <Section heading="Colormaps" class="max-w-240">
    <Sortable.Root
      items={colormaps.groups}
      key={(group) => group.id}
      onReorder={(groups) => colormaps.orderGroups(groups.map((group) => group.id))}
      ariaLabel="Colormap groups"
      containerClass="frame-raised"
      class="flex flex-col"
    >
      {#snippet item(group, index)}
        {@const isOpen = open.has(group.id)}
        <Sortable.Item item={group} class={cn('flex flex-col', index > 0 && 'border-t border-line-faint')}>
          <!-- A click on the row, but not on a control in it, opens or closes the group. The arrow does it from the
          keyboard. -->
          <div
            class={cn('grid min-h-ui-lg cursor-pointer items-center gap-1 pr-2.5 pl-1', rail)}
            role="presentation"
            onclick={(event) => {
              const at = event.target as Element;
              if (at.closest('button, input, [data-control]')) return;
              if (isOpen) open.delete(group.id);
              else open.add(group.id);
            }}
          >
            <span class="flex justify-center" data-control>
              <Sortable.Handle
                item={group}
                class="inline-flex cursor-grab touch-none items-center rounded-sm p-1 text-fg-faint hover:bg-element-hover hover:text-fg active:cursor-grabbing"
              >
                <GripVertical class="size-4" aria-hidden="true" />
              </Sortable.Handle>
            </span>
            <div class="flex min-w-0 items-center gap-1">
              <span class={cn('min-w-0', group.hidden && 'text-fg-muted')} data-control>
                <TextBox
                  size="inline"
                  value={group.label}
                  aria-label="Label of {group.label}"
                  onChange={(text) => colormaps.setLabel(group.id, text.trim())}
                />
              </span>
              <span class="flex-1"></span>
              <Button
                variant="ghost"
                size="xs"
                title={group.hidden ? 'Hidden in the lists to choose from' : 'Shown in the lists to choose from'}
                aria-label="Show {group.label}"
                aria-pressed={!group.hidden}
                onclick={() => colormaps.setHidden(group.id, !group.hidden)}
              >
                {#if group.hidden}
                  <EyeOff class="size-3.5 text-fg-faint" aria-hidden="true" />
                {:else}
                  <Eye class="size-3.5" aria-hidden="true" />
                {/if}
              </Button>
              <Button
                variant="ghost"
                size="xs"
                aria-label="{isOpen ? 'Close' : 'Open'} {group.label}"
                aria-expanded={isOpen}
                onclick={() => (isOpen ? open.delete(group.id) : open.add(group.id))}
              >
                <ChevronDown class={cn('size-3.5 transition-transform', !isOpen && '-rotate-90')} aria-hidden="true" />
              </Button>
            </div>
          </div>
          {#if isOpen}
            <!-- The rows start at the group's name. The line under the grip shows what the group holds. -->
            <div class={cn('grid gap-1 pr-2.5 pb-3 pl-1', rail)}>
              <span class="w-px justify-self-center bg-control-line" aria-hidden="true"></span>
              <div class="flex min-w-0 flex-col gap-3 pt-0.5">
                <div class={rows}>
                  {#each group.ids as id (id)}
                    {@render row(id, group)}
                  {/each}
                </div>
                <div class="flex items-center gap-2">
                  <Popover.Root
                    open={adding === group.id}
                    onOpenChange={(now) => {
                      adding = now ? group.id : null;
                      search = '';
                    }}
                  >
                    <Popover.Trigger>
                      {#snippet child({ props })}
                        <Button {...props} variant="dashed" size="xs">
                          <Plus class="size-3.5" aria-hidden="true" />
                          Add colormap
                        </Button>
                      {/snippet}
                    </Popover.Trigger>
                    <Popover.Content class="flex w-72 flex-col p-0" side="bottom" align="start" sideOffset={4}>
                      <div class="p-2">
                        <TextBox
                          live
                          value={search}
                          onChange={(text) => (search = text)}
                          placeholder="Search colormaps..."
                          aria-label="Search colormaps"
                        />
                      </div>
                      <div class="flex max-h-64 flex-col overflow-y-auto border-t border-line-faint p-1 text-sm">
                        <button
                          type="button"
                          class="flex cursor-pointer items-center gap-2 rounded-sm px-1.5 py-1 text-left hover:bg-element-hover"
                          onclick={() => create(group.id)}
                        >
                          <Plus class="size-3.5 text-fg-muted" aria-hidden="true" />
                          New colormap
                        </button>
                        {#each toAdd(group) as each (each.id)}
                          <button
                            type="button"
                            class="flex cursor-pointer items-center gap-2 rounded-sm px-1.5 py-1 text-left hover:bg-element-hover"
                            onclick={() => colormaps.addTo(group.id, each.id)}
                          >
                            <span
                              class="h-2.5 w-10 shrink-0 rounded-xs border border-line-faint"
                              style:background={colormaps.gradient(each.id)}
                              aria-hidden="true"
                            ></span>
                            <span class="truncate">{each.name}</span>
                          </button>
                        {/each}
                      </div>
                    </Popover.Content>
                  </Popover.Root>
                  <span class="flex-1"></span>
                  {#if group.own}
                    <Button variant="outline" size="xs" onclick={() => colormaps.removeGroup(group.id)}>
                      <Trash class="size-3.5" aria-hidden="true" />
                      Delete group
                    </Button>
                  {:else if group.changed}
                    <Button variant="outline" size="xs" onclick={() => colormaps.resetGroup(group.id)}>
                      <RotateCcw class="size-3.5" aria-hidden="true" />
                      Reset group
                    </Button>
                  {/if}
                </div>
              </div>
            </div>
          {/if}
        </Sortable.Item>
      {/snippet}
    </Sortable.Root>

    {#if colormaps.ungrouped.length > 0}
      <h3 class="px-2.5 pt-3 text-sm text-fg-muted">Not in a group</h3>
      <div class={cn(rows, 'frame-raised p-2.5')}>
        {#each colormaps.ungrouped as id (id)}
          {@render row(id, null)}
        {/each}
      </div>
    {/if}
  </Section>
</div>
