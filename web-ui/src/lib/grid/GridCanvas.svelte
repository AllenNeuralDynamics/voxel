<script lang="ts">
  import type { Component } from 'svelte';

  import { Crosshair, GridLines, PathLight, StackLight } from '$lib/icons';
  import { type Instrument } from '$lib/model';

  import type { LayerVisibility } from './XYPlane.svelte';
  import XYPlane from './XYPlane.svelte';
  import ZPlane from './ZPlane.svelte';

  interface Props {
    instrument: Instrument;
    taskRange?: { start: number; end: number } | null;
  }

  let { instrument, taskRange = null }: Props = $props();

  let layers = $state<LayerVisibility>({ grid: true, tasks: true, path: true, fov: true });

  const layerItems: { key: keyof LayerVisibility; color: string; Icon: Component; title: string }[] = [
    { key: 'grid', color: 'text-fg-muted', Icon: GridLines, title: 'Toggle grid' },
    { key: 'tasks', color: 'text-info', Icon: StackLight, title: 'Toggle tasks' },
    { key: 'path', color: 'text-warning', Icon: PathLight, title: 'Toggle traversal path' },
    { key: 'fov', color: 'text-success', Icon: Crosshair, title: 'Toggle field of view' }
  ];
</script>

{#if instrument.stage}
  <div class="flex h-full min-w-0 flex-col">
    <div class="flex flex-wrap items-center gap-1 border-b border-line-muted px-3 py-2">
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

    <div class="flex min-h-0 min-w-0 flex-1 flex-col gap-4 p-4">
      <div class="flex min-h-0 min-w-0 flex-1">
        <XYPlane {instrument} {taskRange} bind:layers />
      </div>
      <div class="min-h-0 min-w-0 flex-1">
        <ZPlane {instrument} />
      </div>
    </div>
  </div>
{:else}
  <div class="grid h-full w-full place-content-center">
    <p class="text-xl text-fg-muted">Stage not available</p>
  </div>
{/if}
