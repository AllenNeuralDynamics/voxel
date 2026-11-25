<script lang="ts">
  import { getChannelPrefs, getColormaps } from '$lib/context.svelte';
  import { Button, Popover, TextBox } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { isValidHex } from '@voxel/kit/colors';
  import { Check } from '@voxel/kit/icons';

  import { Colormaps } from './colormaps.svelte';

  /**
   * How the image shows 1 channel on 1 camera, in a menu that opens from the channel's dot. The dot has the channel's
   * color. The menu chooses the colormap: 1 from the groups that are shown, as rows of colors and name in 3 columns, found by a search of the names of all colormaps too, a hex color, or
   * auto, which is the color of the light that reaches the camera. `label` names the channel for screen readers.
   */
  interface Props {
    profileId: string;
    channel: string;
    camera: string;
    label: string;
  }

  let { profileId, channel, camera, label }: Props = $props();

  const prefs = getChannelPrefs();
  const colormaps = getColormaps();
  const choice = $derived(prefs.colormap(profileId, channel, camera));
  const color = $derived(prefs.color(profileId, channel, camera));
  const auto = $derived(prefs.autoColor(profileId, channel, camera));
  const choiceName = $derived(
    choice === Colormaps.AUTO ? 'auto' : isValidHex(choice) ? 'custom' : colormaps.name(choice)
  );

  let open = $state(false);
  let search = $state('');
  let searchInput = $state<HTMLInputElement | null>(null);
  let hexInput = $state<HTMLInputElement | null>(null);

  const found = $derived.by(() => {
    const query = search.trim().toLowerCase();
    if (!query) return null;
    // Every colormap, also of a hidden group or of no group, in the order of the groups.
    const ids = new Set([...colormaps.groups.flatMap((group) => group.ids), ...colormaps.all.map((each) => each.id)]);
    return [...ids].filter((id) => colormaps.name(id).toLowerCase().includes(query));
  });

  function pick(value: string): void {
    prefs.setColormap(profileId, channel, camera, value);
    open = false;
  }

  // The text of the custom color box while it is not a color, so the person can correct it.
  let hexText = $state('');
  let hexBad = $state(false);

  /** Uses the typed color, with or without its `#`, in 3 or 6 digits. Text that is no color stays in the box. */
  function applyHex(text: string): void {
    const typed = text.trim();
    const hex = typed.startsWith('#') ? typed : `#${typed}`;
    hexBad = typed !== '' && !isValidHex(hex);
    hexText = hexBad ? text : '';
    if (typed !== '' && !hexBad) pick(hex);
  }
</script>

<!-- A colormap as a row: its colors, then its name. The names of a column start on 1 line. -->
{#snippet swatch(value: string, name: string, gradient: string)}
  <button
    type="button"
    class={cn(
      'flex min-w-0 cursor-pointer items-center gap-1.5 rounded-sm px-1.5 py-1 text-sm text-fg-muted outline-none hover:bg-element-hover hover:text-fg focus-visible:ring-2 focus-visible:ring-focus',
      choice === value && 'bg-element-selected text-fg ring-1 ring-control-line'
    )}
    aria-label="Select colormap {name}"
    aria-pressed={choice === value}
    onclick={() => pick(value)}
  >
    <span class="h-2.5 w-7 shrink-0 rounded-xs border border-line-faint" style:background={gradient}></span>
    <span class="truncate">{name}</span>
  </button>
{/snippet}

<Popover.Root
  bind:open
  onOpenChange={(now) => {
    if (now) return;
    hexText = '';
    hexBad = false;
  }}
>
  <!-- The hit area is larger than the dot, and takes no room in the row. -->
  <Popover.Trigger
    class="-m-1.5 shrink-0 cursor-pointer rounded-sm p-1.5 hover:bg-tint aria-expanded:bg-tint"
    title="Colormap: {choiceName}"
    aria-label="Display of {label} (colormap: {choiceName})"
  >
    <span class="block size-2.5 rounded-full" style:background-color={color}></span>
  </Popover.Trigger>
  <Popover.Content
    class="flex w-auto flex-col p-0"
    side="left"
    align="start"
    sideOffset={12}
    onOpenAutoFocus={(event) => {
      event.preventDefault();
      searchInput?.focus();
    }}
  >
    <!-- The list is first, so it has the most room. What finds or makes a color is 1 row at the foot. -->
    <div class="max-h-96 overflow-y-auto px-2 py-2">
      <div class="swatches">
        {@render swatch(Colormaps.AUTO, 'auto', colormaps.gradient(auto))}
      </div>
      {#if found}
        {#if found.length > 0}
          <div class="swatches pt-2">
            {#each found as id (id)}
              {@render swatch(id, colormaps.name(id), colormaps.gradient(id))}
            {/each}
          </div>
        {:else}
          <div class="px-1.5 pt-2 text-sm text-fg-muted">No matches</div>
        {/if}
      {:else}
        {#each colormaps.shownGroups as group (group.id)}
          <div class="px-1.5 pt-2.5 pb-1 text-sm text-fg-muted">{group.label}</div>
          <div class="swatches">
            {#each group.ids as id (id)}
              {@render swatch(id, colormaps.name(id), colormaps.gradient(id))}
            {/each}
          </div>
        {/each}
      {/if}
    </div>

    <!-- Enter in a box here must not also press the button that gets the focus when the menu closes. -->
    <div
      class="grid grid-cols-[minmax(0,1fr)_8.5rem] gap-1.5 border-t border-line-faint p-2"
      style:--hex-color={color}
      role="presentation"
      onkeydown={(event) => {
        if (event.key === 'Enter') event.preventDefault();
      }}
    >
      <TextBox
        live
        bind:ref={searchInput}
        value={search}
        onChange={(text) => (search = text)}
        placeholder="Search colormaps..."
        aria-label="Search colormaps"
        class="min-w-0"
      />
      <TextBox
        bind:ref={hexInput}
        value={hexText}
        onChange={applyHex}
        placeholder={color}
        aria-label="Custom hex color"
        aria-invalid={hexBad}
        class={cn('min-w-0 border-l-[3px] border-l-(--hex-color) font-mono', hexBad && 'ring-danger-fg!')}
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
          <Check class="size-3.5" aria-hidden="true" />
        </Button>
      </TextBox>
    </div>
  </Popover.Content>
</Popover.Root>

<style>
  .swatches {
    display: grid;
    /* The menu is as wide as its 3 columns. A column holds the colors and the longest name. */
    grid-template-columns: repeat(3, 8rem);
    gap: 0.125rem 0.25rem;
  }
</style>
