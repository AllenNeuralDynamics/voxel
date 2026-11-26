<script lang="ts">
  import type { SpecimenAxis } from '$lib/core/types';
  import type { UnitSteps } from '$lib/features/run/StageNumericField.svelte';
  import { ContextMenu } from '@voxel/kit';

  interface Props {
    axis: SpecimenAxis;
    /** Where the stage can go on this axis, in µm. */
    travel: [number, number];
    /** Where the specimen can be imaged on it; the travel when the rig names no range. */
    specimen: [number, number];
    /** The selected task's reach on this axis. */
    spans?: [number, number][];
    stage?: number;
    target?: number | null;
    unit: UnitSteps;
    disabled?: boolean;
    onmove?: (value: number) => void;
  }

  let { axis, travel, specimen, spans = [], stage, target = null, unit, disabled = false, onmove }: Props = $props();

  // Its own window: the specimen range until it is zoomed or panned, then a window inside the travel.
  let zoomed = $state<[number, number] | null>(null);
  const shown = $derived(zoomed ?? specimen);
  const [lo, hi] = $derived(shown);
  let track = $state<HTMLDivElement>();
  let panFrom: { y: number; window: [number, number] } | null = null;
  let menuAt = $state<number | null>(null);
  let hover = $state<number | null>(null);
  const EPSILON = 1e-6;
  // The travel past the specimen range, inside the window: dashed sides above and below the specimen.
  const above = $derived<[number, number] | null>(
    specimen[1] < hi && travel[1] > specimen[1] ? [Math.max(specimen[1], lo), Math.min(travel[1], hi)] : null
  );
  const below = $derived<[number, number] | null>(
    specimen[0] > lo && travel[0] < specimen[0] ? [Math.max(travel[0], lo), Math.min(specimen[0], hi)] : null
  );

  /** From the top of the track, in %. */
  function at(value: number): number {
    return 100 - ((Math.max(lo, Math.min(hi, value)) - lo) / (hi - lo)) * 100;
  }

  function valueAt(clientY: number): number {
    const rect = track!.getBoundingClientRect();
    return hi - ((clientY - rect.top) / rect.height) * (hi - lo);
  }

  function limited(a: number, b: number): [number, number] {
    const size = Math.min(b - a, travel[1] - travel[0]);
    const start = Math.max(travel[0], Math.min(travel[1] - size, a));
    return [start, start + size];
  }

  function zoom(event: WheelEvent) {
    event.preventDefault();
    const pivot = valueAt(event.clientY);
    const factor = Math.exp(event.deltaY * 0.0015);
    const smallest = (specimen[1] - specimen[0]) / 30;
    const size = Math.max(smallest, Math.min(travel[1] - travel[0], (hi - lo) * factor));
    const share = (pivot - lo) / (hi - lo);
    zoomed = limited(pivot - share * size, pivot - share * size + size);
  }

  /** `up` or `down` when `value` is outside the window: its mark then sits at that end with an arrow. */
  function outside(value: number): 'up' | 'down' | null {
    return value > hi + EPSILON ? 'up' : value < lo - EPSILON ? 'down' : null;
  }

  function label(value: number): string {
    return (value / unit.scale).toFixed(unit.scale === 1 ? 0 : 2);
  }
</script>

{#snippet mark(value: number, dashed: boolean)}
  {@const out = outside(value)}
  <i
    class={[
      'pointer-events-none absolute -inset-x-1.5 h-0.5 -translate-y-1/2',
      dashed
        ? 'bg-[repeating-linear-gradient(to_right,var(--fg)_0_4px,transparent_4px_7px)] opacity-70'
        : 'bg-fg opacity-80'
    ]}
    style:top="{at(value)}%"
    title={dashed ? undefined : `${axis.toUpperCase()} ${label(value)} ${unit.label}`}
  >
    {#if out}
      <span
        class={[
          'absolute left-1/2 size-0 -translate-x-1/2 border-x-4 border-x-transparent',
          out === 'up' ? 'bottom-0.75 border-b-4 border-b-fg' : 'top-0.75 border-t-4 border-t-fg'
        ]}
      ></span>
    {/if}
  </i>
{/snippet}

<div class="flex w-14 shrink-0 flex-col items-center gap-1 bg-pane py-4 text-sm text-fg-faint">
  <span>{unit.label}</span>
  <span class="tabular-nums">{label(hi)}</span>
  <ContextMenu.Root>
    <ContextMenu.Trigger>
      {#snippet child({ props })}
        <div
          {...props}
          bind:this={track}
          role="slider"
          tabindex="-1"
          aria-label="{axis.toUpperCase()} position"
          aria-valuenow={stage}
          aria-valuemin={travel[0]}
          aria-valuemax={travel[1]}
          class="relative w-4 flex-1 cursor-grab touch-none bg-[color-mix(in_oklab,var(--fg)_2.5%,var(--pane))]"
          onwheel={zoom}
          onpointerdown={(event) => {
            if (event.button === 2) menuAt = valueAt(event.clientY);
            if (event.button !== 0) return;
            if (event.altKey) {
              if (!disabled) onmove?.(valueAt(event.clientY));
              return;
            }
            panFrom = { y: event.clientY, window: [lo, hi] };
            track?.setPointerCapture(event.pointerId);
          }}
          onpointermove={(event) => {
            hover = valueAt(event.clientY);
            if (!panFrom || !track) return;
            const per = (panFrom.window[1] - panFrom.window[0]) / track.getBoundingClientRect().height;
            const shift = (event.clientY - panFrom.y) * per;
            zoomed = limited(panFrom.window[0] + shift, panFrom.window[1] + shift);
          }}
          onpointerup={() => (panFrom = null)}
          onpointerleave={() => (hover = null)}
        >
          {#each [above, below] as side, index (index)}
            {#if side}
              {#each ['left-0', 'right-0'] as edge (edge)}
                <i
                  class="pointer-events-none absolute {edge} w-px bg-[repeating-linear-gradient(to_bottom,var(--line-muted)_0_4px,transparent_4px_8px)]"
                  style:top="{at(side[1])}%"
                  style:bottom="{100 - at(side[0])}%"
                ></i>
              {/each}
            {/if}
          {/each}
          {#if hi >= travel[1] - EPSILON}
            <i
              class="pointer-events-none absolute inset-x-0 top-0 h-px bg-[repeating-linear-gradient(to_right,var(--line-muted)_0_4px,transparent_4px_8px)]"
            ></i>
          {/if}
          {#if lo <= travel[0] + EPSILON}
            <i
              class="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-[repeating-linear-gradient(to_right,var(--line-muted)_0_4px,transparent_4px_8px)]"
            ></i>
          {/if}
          {#if specimen[1] >= lo && specimen[0] <= hi}
            <i
              class={[
                'pointer-events-none absolute inset-x-0 bg-[color-mix(in_oklab,var(--fg)_2.5%,transparent)] shadow-[inset_1px_0_var(--line-faint),inset_-1px_0_var(--line-faint)]',
                specimen[1] <= hi + EPSILON && 'border-t border-line-faint',
                specimen[0] >= lo - EPSILON && 'border-b border-line-faint'
              ]}
              style:top="{at(specimen[1])}%"
              style:bottom="{100 - at(specimen[0])}%"
            ></i>
          {/if}
          {#each spans as [a, b], index (index)}
            {#if b >= lo && a <= hi}
              <i
                class="pointer-events-none absolute inset-x-0.5 min-h-0.5 bg-[color-mix(in_oklab,var(--accent-fg)_14%,transparent)] shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--accent-fg)_50%,transparent)]"
                style:top="{at(b)}%"
                style:bottom="{100 - at(a)}%"
              ></i>
            {/if}
          {/each}
          {#if target !== null}
            {@render mark(target, true)}
          {/if}
          {#if stage !== undefined}
            {@render mark(stage, false)}
          {/if}
          {#if hover !== null}
            <i class="pointer-events-none absolute -inset-x-1.5 h-px bg-fg-faint" style:top="{at(hover)}%"></i>
            <!-- The track is 1rem wide in the middle of the 3.5rem strip, so this sits just past the strip's edge. -->
            <span
              class="pointer-events-none absolute left-[calc(100%+1.75rem)] z-10 -translate-y-1/2 frame-floating px-1.5 py-0.5 font-mono text-xs whitespace-nowrap text-fg tabular-nums"
              style:top="{at(hover)}%"
            >
              {axis.toUpperCase()}
              {(hover / unit.scale).toFixed(unit.decimals)}
              {unit.label}
            </span>
          {/if}
        </div>
      {/snippet}
    </ContextMenu.Trigger>
    <ContextMenu.Content class="min-w-52">
      {#if menuAt !== null}
        {@const value = menuAt}
        <div class="px-2 py-1.5 font-mono text-sm text-fg-muted tabular-nums">
          {axis.toUpperCase()}
          {(value / unit.scale).toFixed(unit.decimals)}
          {unit.label}
        </div>
        <ContextMenu.Item {disabled} onSelect={() => onmove?.(value)}>Move the stage here</ContextMenu.Item>
        <ContextMenu.Separator />
      {/if}
      <ContextMenu.Item
        disabled={stage === undefined}
        onSelect={() => stage !== undefined && (zoomed = limited(stage - (hi - lo) / 2, stage + (hi - lo) / 2))}
      >
        Pan to current position
      </ContextMenu.Item>
      <ContextMenu.Item onSelect={() => (zoomed = null)}>Fit to the specimen range</ContextMenu.Item>
      <ContextMenu.Item onSelect={() => (zoomed = [...travel])}>Fit to the stage travel</ContextMenu.Item>
    </ContextMenu.Content>
  </ContextMenu.Root>
  <span class="tabular-nums">{label(lo)}</span>
  <span class="font-mono font-medium" style:color="var(--axis-{axis})">{axis.toUpperCase()}</span>
</div>
