<script lang="ts">
  import type { Component } from 'svelte';
  import type { SvelteHTMLElements } from 'svelte/elements';
  import { toast } from 'svelte-sonner';

  import { reportFailure } from '$lib/core/failures';
  import { TextBox } from '$lib/kit';
  import * as icons from '$lib/kit/icons';
  import { Flashlight, Microscope, Video } from '$lib/kit/icons';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';

  type Icon = Component<SvelteHTMLElements['svg']>;

  const ALL = Object.entries(icons as Record<string, Icon>).sort(([a], [b]) => a.localeCompare(b));
  const SIZES = ['size-3', 'size-3.5', 'size-4', 'size-5', 'size-6'];
  const IN_USE = [Microscope, Flashlight, Video];

  let query = $state('');
  const shown = $derived(ALL.filter(([name]) => name.toLowerCase().includes(query.trim().toLowerCase())));

  function copy(name: string): void {
    reportFailure(navigator.clipboard.writeText(name).then(() => toast.success(`Copied ${name}`)));
  }
</script>

<LabHeader title="Icons">
  {#snippet trailing()}
    <span class="text-sm text-fg-muted tabular-nums">{shown.length} of {ALL.length}</span>
    <TextBox
      live
      size="sm"
      value={query}
      onChange={(text) => (query = text)}
      placeholder="Filter"
      aria-label="Filter icons"
      class="w-56"
    />
  {/snippet}
</LabHeader>

<div class={lab.body}>
  <section class={lab.section}>
    <h2 class={lab.heading}>Sizes</h2>
    <div class="flex flex-wrap items-end gap-x-10 gap-y-4 px-1">
      {#each SIZES as size (size)}
        <figure class="flex flex-col items-center gap-3">
          <span class="flex items-end gap-2 text-fg">
            {#each IN_USE as Glyph, index (index)}<Glyph class={size} />{/each}
          </span>
          <figcaption class={lab.code}>{size}</figcaption>
        </figure>
      {/each}
      <figure class="flex flex-col items-center gap-3">
        <span class="flex items-end gap-2 text-fg">
          {#each IN_USE as Glyph, index (index)}<Glyph class="size-6 **:stroke-[1.25]" />{/each}
        </span>
        <figcaption class={lab.code}>size-6, stroke 1.25</figcaption>
      </figure>
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Set</h2>
    {#if shown.length}
      <ul class="grid grid-cols-[repeat(auto-fill,minmax(7.5rem,1fr))] gap-1">
        {#each shown as [name, Glyph] (name)}
          <li>
            <button
              type="button"
              class="flex h-24 w-full flex-col items-center justify-center gap-3 rounded-lg text-fg-muted transition-colors hover:bg-tint-hover hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
              title="Copy {name}"
              onclick={() => copy(name)}
            >
              <Glyph class="size-5" aria-hidden="true" />
              <span class="max-w-full truncate px-2 text-xs">{name}</span>
            </button>
          </li>
        {/each}
      </ul>
    {:else}
      <p class="px-1 text-base text-fg-muted">No icon matches “{query}”.</p>
    {/if}
  </section>
</div>
