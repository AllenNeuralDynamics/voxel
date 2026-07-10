<script lang="ts">
  import { CameraHandle, type Instrument } from '$lib/model';
  import { cn, sanitizeString } from '$lib/utils';

  import { deviceIdentity } from './snippets.svelte';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  let { instrument, class: className }: Props = $props();

  const allCameras = $derived([...instrument.cameras.values()]);

  /** The active-profile channel this camera provides detection for, if any. */
  const channelOf = (id: string) => instrument.activeChannels.find((c) => c.camera.id === id);

  // In-profile cameras first (what the active profile images with), then the rest — profile rows carry a channel chip.
  const sortedCameras = $derived([
    ...allCameras.filter((c) => channelOf(c.id) !== undefined),
    ...allCameras.filter((c) => channelOf(c.id) === undefined)
  ]);
</script>

<div class={cn('flex w-full min-w-68 flex-col py-2', className)}>
  <div class="flex shrink-0 items-center gap-2 px-3 py-1">
    <span class="text-xs font-medium tracking-wide text-fg-muted uppercase">Cameras</span>
    <div class="flex-1"></div>
    <span class="font-mono text-[10px] text-fg-faint tabular-nums">{allCameras.length}</span>
  </div>

  <div class="flex flex-col gap-4 px-3 py-2">
    {#if sortedCameras.length > 0}
      {#each sortedCameras as cam (cam.id)}
        {@render cameraRow(cam)}
      {/each}
    {:else}
      <p class="text-xs text-fg-muted/60">No cameras.</p>
    {/if}
  </div>
</div>

{#snippet cameraRow(cam: CameraHandle)}
  {@const info = cam.streamInfo}
  {@const channel = channelOf(cam.id)}
  {@const frame = cam.frameSizePx}
  {@const sizeMb = cam.frameSizeMb?.value}
  {@const fill = cam.bufferFill}
  {@const dropped = info?.dropped_frames ?? 0}
  <div class="flex flex-col overflow-hidden rounded-xs border border-border bg-card">
    <!-- row 1: identity + geometry -->
    <div class="flex items-center gap-2 px-2.5 pt-2 pb-1.5">
      {@render deviceIdentity(sanitizeString(cam.id), channel)}
      <span class="ml-auto font-mono text-[10px] text-fg-muted tabular-nums">
        {frame ? `${frame.x}×${frame.y}` : '—'}{#if typeof sizeMb === 'number'}
          · {sizeMb.toFixed(1)} MB{/if}
      </span>
    </div>

    <!-- row 2: status — mode dot leads the live rates, or "Idle" -->
    <div class="flex h-12 flex-col gap-1 border-t border-border px-2.5 py-1.5">
      {#snippet modeDot()}
        <span
          class={cn(
            'h-1.5 w-1.5 shrink-0 rounded-full',
            cam.mode === 'PREVIEW' ? 'bg-success' : cam.mode === 'ACQUISITION' ? 'bg-warning' : 'bg-fg-muted/40'
          )}
        ></span>
      {/snippet}
      <div class="flex items-center justify-between">
        {#if info}
          <span class="flex items-center gap-3.5 font-mono text-[10px] tabular-nums">
            {@render stat('fps', info.frame_rate_fps.toFixed(1))}
            {@render stat('MB/s', info.data_rate_mbs.toFixed(1))}
          </span>
        {:else}
          <span class="text-[11px] text-fg-muted">Idle</span>
        {/if}
        {@render modeDot()}
      </div>
      {#if info}
        <div class="flex items-center justify-between font-mono text-[10px] tabular-nums">
          {@render stat('dropped', String(dropped), dropped > 0)}
          {#if fill != null}
            {@render stat('buf', `${(fill * 100).toFixed(0)}%`)}
          {/if}
        </div>
      {/if}
    </div>
  </div>
{/snippet}

{#snippet stat(label: string, value: string, danger?: boolean)}
  <span class="flex items-baseline gap-1">
    <span class={danger ? 'text-danger' : 'text-fg'}>{value}</span>
    <span class="text-fg-muted/60">{label}</span>
  </span>
{/snippet}
