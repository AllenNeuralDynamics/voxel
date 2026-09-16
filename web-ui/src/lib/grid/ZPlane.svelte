<script lang="ts">
  import { onMount } from 'svelte';

  import type { Instrument } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import { formatSpatialDistance } from '$lib/spatial-units';

  import { getTaskSelection } from './selection.svelte';

  interface Props {
    instrument: Instrument;
  }

  let { instrument }: Props = $props();

  let containerRef = $state<HTMLDivElement | null>(null);
  let panelWidth = $state(400);
  let panelHeight = $state(250);

  const taskSelection = getTaskSelection();

  const z = $derived(instrument.stage.z);
  const zPos = $derived(z?.position?.value ?? 0);
  const zLower = $derived(z?.lowerLimit?.value ?? 0);
  const zUpper = $derived(z?.upperLimit?.value ?? 0);
  const zMoving = $derived(z?.isMoving?.value === true);
  const depth = $derived(z?.range ?? 0);
  const activeProfileId = $derived(instrument.activeProfileId);

  const tasks = $derived(instrument.state.tasks);
  const taskTiles = $derived(instrument.taskTiles);

  function isActive(taskId: string): boolean {
    return activeProfileId ? (tasks[taskId]?.profile_ids.includes(activeProfileId) ?? false) : false;
  }

  const fovZ = $derived(z ? zPos - zLower : 0);
  const zLineX = $derived(depth > 0 ? (fovZ / depth) * panelWidth : 0);
  const stageTarget = $derived(instrument.stage.target);
  const targetPending = $derived(instrument.stage.targetPending);
  const displayValue = $derived(targetPending && stageTarget?.z != null ? stageTarget.z : zPos);

  function oninput(e: Event) {
    const v = parseFloat((e.target as HTMLInputElement).value);
    instrument.stage.moveTo({ z: v });
  }

  onMount(() => {
    if (!containerRef) return;
    const observer = new ResizeObserver(([entry]) => {
      const w = entry.contentRect.width;
      const h = entry.contentRect.height;
      if (w > 0) panelWidth = w;
      if (h > 0) panelHeight = h;
    });
    observer.observe(containerRef);
    return () => observer.disconnect();
  });
</script>

<div
  bind:this={containerRef}
  class="relative h-full w-full border border-line-faint transition-colors duration-300 ease-in-out hover:bg-floating/75"
>
  <p class="absolute top-1 right-1 z-10 text-fg-muted">Z</p>

  {#if z}
    <input
      type="range"
      class="stage-slider absolute inset-0 z-10 h-full w-full"
      style:--thumb-length="{panelHeight}px"
      min={zLower}
      max={zUpper}
      step={10}
      value={displayValue}
      disabled={zMoving}
      {oninput}
    />
  {/if}

  <svg
    viewBox="0 0 {panelWidth} {panelHeight}"
    class="pointer-none absolute inset-0 z-0"
    preserveAspectRatio="none"
    width="100%"
    height="100%"
  >
    {#each taskTiles as tile (tile.task_id)}
      {@const t = tasks[tile.task_id]}
      {#if t}
        {@const selected = taskSelection.has(tile.task_id)}
        {@const active = isActive(tile.task_id)}
        {@const z0X = depth > 0 ? ((t.start - zLower) / depth) * panelWidth : 0}
        {@const z1X = depth > 0 ? ((t.end - zLower) / depth) * panelWidth : 0}
        <g
          class="text-fg"
          stroke-width={selected ? '1.5' : '0.5'}
          stroke="currentColor"
          opacity={selected ? 1 : active ? 0.3 : 0.15}
        >
          <line class="nss" x1={z0X} y1="0" x2={z0X} y2={panelHeight} />
          <line class="nss" x1={z1X} y1="0" x2={z1X} y2={panelHeight} />
        </g>
      {/if}
    {/each}
    <line
      x1={zLineX}
      y1="0"
      x2={zLineX}
      y2={panelHeight}
      class="nss"
      stroke-width="1"
      stroke={zMoving ? 'var(--color-danger)' : 'var(--color-success)'}
    >
      <title>Z: {formatSpatialDistance(zPos, prefs.spatialUnit.get())}</title>
    </line>
  </svg>
</div>

<style>
  .stage-slider {
    -webkit-appearance: none;
    appearance: none;
    cursor: pointer;
    margin: 0;
    padding: 0;
    border: none;
    background-color: transparent;
    --_track-color: var(--color-control-line);
    --_track-width: 1px;

    &::-webkit-slider-runnable-track {
      background: transparent;
      border-radius: 0;
    }
    &::-moz-range-track {
      background: transparent;
      border-radius: 0;
    }
    &::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      inline-size: 1px;
      block-size: var(--thumb-length);
      border-radius: 1px;
      cursor: pointer;
      background: transparent;
    }
    &::-moz-range-thumb {
      appearance: none;
      inline-size: 1px;
      block-size: var(--thumb-length);
      border: none;
      border-radius: 1px;
      cursor: pointer;
      background: transparent;
    }
    &:disabled {
      cursor: not-allowed;
      &::-webkit-slider-thumb {
        background: var(--color-danger);
      }
      &::-moz-range-thumb {
        background: var(--color-danger);
      }
    }
  }
</style>
