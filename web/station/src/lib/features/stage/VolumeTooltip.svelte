<script lang="ts">
  import type { StagePlan, Tile } from './stage-plan.svelte';

  interface Props {
    tile: Tile;
    plan: StagePlan;
    /** The volume that runs now, while a run is on. */
    visit?: number | null;
    x: number;
    y: number;
    width: number;
    height: number;
  }

  let { tile, plan, visit = null, x, y, width, height }: Props = $props();

  let box = $state<HTMLDivElement>();
  const numbers = $derived(tile.volumes.map((index) => index + 1));
  const run = $derived(
    numbers.length > 1 && numbers.at(-1)! - numbers[0] === numbers.length - 1
      ? `${numbers[0]}–${numbers.at(-1)}`
      : numbers.join(', ')
  );
  const profiles = $derived([...new Set(tile.volumes.map((index) => plan.volumes[index]?.profile))].join(', '));
  const status = $derived(
    visit === null
      ? 'Planned'
      : tile.volumes.includes(visit)
        ? 'Running'
        : tile.volumes.every((index) => index < visit)
          ? 'Completed'
          : 'Pending'
  );
  const left = $derived(Math.max(8, Math.min(x + 12, width - (box?.offsetWidth ?? 160) - 8)));
  const top = $derived(y + 16 + (box?.offsetHeight ?? 80) > height - 8 ? y - (box?.offsetHeight ?? 80) - 10 : y + 16);
</script>

<div
  bind:this={box}
  role="tooltip"
  class="pointer-events-none absolute z-20 frame-floating px-2.5 py-2 text-sm"
  style:left="{left}px"
  style:top="{top}px"
>
  <p class="mb-1 font-mono text-fg">{tile.task}</p>
  <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5">
    <dt class="text-fg-muted">{numbers.length === 1 ? 'Volume' : 'Volumes'}</dt>
    <dd class="tabular-nums">{run}</dd>
    <dt class="text-fg-muted">{profiles.includes(',') ? 'Profiles' : 'Profile'}</dt>
    <dd class="font-mono">{profiles}</dd>
    <dt class="text-fg-muted">Status</dt>
    <dd>{status}</dd>
  </dl>
</div>
