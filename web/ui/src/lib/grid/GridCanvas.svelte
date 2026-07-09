<script lang="ts">
  import type { Component } from 'svelte';

  import { GridLines, ImageLight, PathLight, StackLight } from '$lib/icons';
  import { type Instrument } from '$lib/model';
  import StencilControls from '$lib/StencilControlsInline.svelte';

  import type { LayerVisibility } from './XYPlane.svelte';
  import XYPlane from './XYPlane.svelte';
  import ZPlane from './ZPlane.svelte';

  interface Props {
    instrument: Instrument;
  }

  let { instrument }: Props = $props();

  let layers = $state<LayerVisibility>({ grid: true, tasks: true, path: true, fov: true, thumbnail: true });

  const layerItems: { key: keyof LayerVisibility; color: string; Icon: Component; title: string }[] = [
    { key: 'grid', color: 'text-fg-muted', Icon: GridLines, title: 'Toggle grid' },
    { key: 'tasks', color: 'text-info', Icon: StackLight, title: 'Toggle tasks' },
    { key: 'path', color: 'text-warning', Icon: PathLight, title: 'Toggle traversal path' },
    { key: 'thumbnail', color: 'text-success', Icon: ImageLight, title: 'Toggle thumbnail' }
  ];
</script>

{#if instrument.stage.x && instrument.stage.y && instrument.stage.z}
  <div class="flex h-full min-w-0 flex-col">
    <div class="flex min-h-0 min-w-0 flex-1 items-stretch gap-4 p-4">
      <XYPlane {instrument} bind:layers />
      <ZPlane {instrument} />
    </div>

    <!-- Grid controls footer: layer toggles + grid stencil -->
    <div class="flex w-full flex-wrap items-stretch gap-7 border-t border-border">
      <StencilControls {instrument} />
      <div class="ml-auto flex items-center gap-1 pr-4">
        {#each layerItems as { key, color, Icon, title } (key)}
          <button
            onclick={() => (layers[key] = !layers[key])}
            class="cursor-pointer rounded-full p-1 transition-colors {layers[key] ? `${color}` : 'text-fg-faint'}"
            {title}
          >
            <Icon width="14" height="14" />
          </button>
        {/each}
      </div>
    </div>
  </div>
{:else}
  <div class="grid h-full w-full place-content-center">
    <p class="text-base text-fg-muted">Stage not available</p>
  </div>
{/if}
