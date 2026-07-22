<script lang="ts">
  import { onMount } from 'svelte';

  import type { Instrument } from '$lib/model';

  import { getTaskSelection } from './selection.svelte';

  interface Props {
    instrument: Instrument;
  }

  let { instrument }: Props = $props();

  const PANEL_WIDTH = 64;

  let containerRef = $state<HTMLDivElement | null>(null);
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
  const zLineY = $derived(depth > 0 ? (1 - fovZ / depth) * panelHeight - 1 : 0);
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
      const h = entry.contentRect.height;
      if (h > 0) panelHeight = h;
    });
    observer.observe(containerRef);
    return () => observer.disconnect();
  });
</script>

<div
  bind:this={containerRef}
  class="relative h-full flex-none border border-border-faint transition-colors duration-300 ease-in-out hover:bg-floating/75"
  style="width: {PANEL_WIDTH}px"
>
  <p class="absolute top-1 right-1 z-10 text-fg-muted">Z</p>

  {#if z}
    <input
      type="range"
      class="stage-slider absolute inset-0 z-10 h-full w-full"
      style:--thumb-length="{PANEL_WIDTH}px"
      min={zLower}
      max={zUpper}
      step={10}
      value={displayValue}
      disabled={zMoving}
      {oninput}
    />
  {/if}

  <svg
    viewBox="0 0 {PANEL_WIDTH} {panelHeight}"
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
        {@const z0Y = depth > 0 ? (1 - (t.start - zLower) / depth) * panelHeight - 1 : 0}
        {@const z1Y = depth > 0 ? (1 - (t.end - zLower) / depth) * panelHeight - 1 : 0}
        <g
          class="text-fg"
          stroke-width={selected ? '1.5' : '0.5'}
          stroke="currentColor"
          opacity={selected ? 1 : active ? 0.3 : 0.15}
        >
          <line class="nss" x1="0" y1={z0Y} x2={PANEL_WIDTH} y2={z0Y} />
          <line class="nss" x1="0" y1={z1Y} x2={PANEL_WIDTH} y2={z1Y} />
        </g>
      {/if}
    {/each}
    <line
      x1="0"
      y1={zLineY}
      x2={PANEL_WIDTH}
      y2={zLineY}
      class="nss"
      stroke-width="1"
      stroke={zMoving ? 'var(--color-danger)' : 'var(--color-success)'}
    >
      <title>Z: {(zPos / 1000).toFixed(3)} mm</title>
    </line>
  </svg>
</div>

<style>
  .stage-slider {
    -webkit-appearance: none;
    appearance: none;
    writing-mode: vertical-rl;
    direction: rtl;
    cursor: pointer;
    margin: 0;
    padding: 0;
    border: none;
    background-color: transparent;
    --_track-color: var(--color-border);
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
