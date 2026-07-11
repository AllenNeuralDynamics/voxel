<script lang="ts">
  import { Rename } from '$lib/kit';
  import type { Preview, Snapshot } from '$lib/model';

  interface Props {
    snap: Snapshot;
    previewer: Preview;
    onRename?: (label: string) => void;
  }

  let { snap, previewer, onRename }: Props = $props();

  const channelEntries = $derived(Object.entries(snap.channels));

  /** Round to at most `d` decimals and drop trailing zeros (9.96999… → 9.97, 10.0 → 10). */
  function num(value: number, d: number): string {
    return String(parseFloat(value.toFixed(d)));
  }
</script>

<div
  class="pointer-events-none flex w-56 flex-col divide-y divide-border/50 overflow-hidden rounded-xs border border-border/50 bg-floating/90 text-xs shadow-lg backdrop-blur-sm"
>
  <!-- Name (double-click to rename) + profile -->
  <div class="flex min-h-8 items-center justify-between gap-2 px-2.5">
    <div class="pointer-events-auto min-w-0">
      <Rename value={snap.label} size="sm" class="font-medium text-fg" textClass="truncate" onSave={(v) => onRename?.(v)} />
    </div>
    {#if snap.profileLabel}
      <span class="shrink-0 rounded bg-element-bg px-1.5 py-0.5 text-fg-muted">{snap.profileLabel}</span>
    {/if}
  </div>

  {#each channelEntries as [name, ch] (name)}
    {@const color = previewer.resolveColor(ch.colormap) ?? 'var(--color-fg-muted)'}
    <div class="flex flex-col gap-1 px-2.5 py-2">
      <div class="flex items-center gap-1.5">
        <span class="h-2 w-2 shrink-0 rounded-full" style:background-color={color}></span>
        <span class="truncate font-medium text-fg">{ch.label}</span>
      </div>
      <dl class="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
        <dt class="text-fg-muted">Levels</dt>
        <dd class="text-right text-fg tabular-nums">
          {(ch.levelsMin * 100).toFixed(0)}–{(ch.levelsMax * 100).toFixed(0)}%
        </dd>
        {#if ch.detection?.exposureTime != null}
          <dt class="text-fg-muted">Exposure</dt>
          <dd class="text-right text-fg tabular-nums">{num(ch.detection.exposureTime, 2)} ms</dd>
        {/if}
        {#if ch.detection?.binning != null}
          <dt class="text-fg-muted">Binning</dt>
          <dd class="text-right text-fg tabular-nums">{ch.detection.binning}×</dd>
        {/if}
        {#if ch.illumination?.powerSetpoint != null}
          <dt class="text-fg-muted">Power</dt>
          <dd class="text-right text-fg tabular-nums">{num(ch.illumination.powerSetpoint, 1)} mW</dd>
        {/if}
      </dl>
    </div>
  {/each}
</div>
