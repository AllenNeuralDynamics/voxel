<script lang="ts">
  import { useThrottle, watch } from 'runed';
  import { onMount } from 'svelte';

  import { Eraser, Plus, Record, TrashCanOutline, VectorCombine } from '$lib/icons';
  import { Button, ContextMenu, Rename } from '$lib/kit';
  import { getVoxelApp, type InpaintMosaic } from '$lib/model';
  import { cn, toastError } from '$lib/utils';

  import type { Bounds, Painter } from '../draw';
  import { getStageScene, type StageLayer, useLayer } from '../scene.svelte';

  // A marquee region resolved against the viewed mosaics: the erase rect (µm) + the mosaics/channels it clears.
  interface EraseHit {
    mosaicIds: string[];
    rect: { x: number; y: number; w: number; h: number };
    channels: string[];
  }

  const app = getVoxelApp();
  const inpaint = app.inpaint;
  const scene = getStageScene();
  const stage = $derived(app.instrument?.stage ?? null);
  const instrument = $derived(app.instrument);

  const list = $derived(inpaint.list);
  const activeId = $derived(inpaint.activeMosaic?.id ?? null);
  const viewedList = $derived(inpaint.viewedList);
  const recording = $derived((instrument?.mode ?? 'idle') !== 'idle'); // previewing or acquiring = live paint

  const MAX_UPSCALE = 4; // don't upscale mosaic pixels past this
  const OVERVIEW_PX = 2048; // matches InpaintRaster OVERVIEW_MAX — overview long-axis resolution

  type Rect = { x: number; y: number; w: number; h: number };

  // Union of channel names across mosaics, first-seen order (plain object avoids a reactive-Set lint).
  function unionChannels(mosaics: InpaintMosaic[]): string[] {
    const seen: Record<string, true> = {};
    for (const m of mosaics) for (const ch of Object.keys(m.channels)) seen[ch] = true;
    return Object.keys(seen);
  }

  // Draw one mosaic's channel into `acc` — cap-level patches when zoomed past overview resolution, else overview.
  function drawMosaicChannel(acc: Painter, m: InpaintMosaic, channel: string, view: Rect) {
    const scale = 1 / acc.px(1); // camera px per µm
    if (scale > OVERVIEW_PX / Math.max(m.stage.w, m.stage.h)) {
      for (const patch of inpaint.patches(m.id, channel, view)) {
        acc.image(patch.canvas, patch.originX, patch.originY, patch.sizeUm, patch.sizeUm);
      }
    } else {
      const ov = inpaint.overview(m.id, channel);
      if (ov) acc.image(ov, m.stage.x, m.stage.y, m.stage.w, m.stage.h);
    }
  }

  // ── Layer: the viewed mosaics, composited. Additive across channels; within a shared channel, weighted-max
  //    across mosaics (brightest wins), matching the intra-mosaic projection.
  const draw = (p: Painter) => {
    const mosaics = viewedList;
    if (mosaics.length === 0) return;
    const b = p.viewBounds();
    const view = { x: b.minX, y: b.minY, w: b.maxX - b.minX, h: b.maxY - b.minY };
    const single = mosaics.length === 1;

    for (const channel of unionChannels(mosaics)) {
      p.pass('lighter', (acc) => {
        if (single) {
          const m = mosaics[0];
          const w = m.channels[channel]?.weight ?? 0;
          if (w <= 0) return;
          acc.globalAlpha = w;
          drawMosaicChannel(acc, m, channel, view);
        } else {
          for (const m of mosaics) {
            const w = m.channels[channel]?.weight ?? 0;
            if (w <= 0) continue;
            acc.pass('lighten', (mx) => {
              mx.globalAlpha = w;
              drawMosaicChannel(mx, m, channel, view);
            });
          }
        }
      });
    }
  };

  function mosaicMaxScale(): number | null {
    let best = 0;
    for (const m of viewedList) if (m.umPerPx > 0) best = Math.max(best, 1 / m.umPerPx);
    return best > 0 ? best * MAX_UPSCALE : null;
  }

  // Resolve a marquee region against the viewed mosaics it overlaps; erase acts on all of them at once.
  function hitMarquee(rect: Bounds): EraseHit | null {
    const hit = viewedList.filter(
      (m) =>
        rect.maxX > m.stage.x &&
        rect.minX < m.stage.x + m.stage.w &&
        rect.maxY > m.stage.y &&
        rect.minY < m.stage.y + m.stage.h
    );
    if (hit.length === 0) return null;
    const channels = unionChannels(hit);
    if (channels.length === 0) return null;
    return {
      mosaicIds: hit.map((m) => m.id),
      rect: { x: rect.minX, y: rect.minY, w: rect.maxX - rect.minX, h: rect.maxY - rect.minY },
      channels
    };
  }

  const layer: StageLayer<EraseHit> = {
    id: 'inpaint',
    z: -1, // beneath the snapshots layer (z 0) — a background navigation map
    get visible() {
      return viewedList.length > 0;
    },
    draw,
    hitMarquee,
    marqueeMenu: eraseMenu,
    maxScale: mosaicMaxScale
  };
  useLayer(layer);

  onMount(() => {
    inpaint.onChange = () => scene.invalidate();
    return () => {
      inpaint.onChange = null;
    };
  });

  // Redraw when the viewed mosaics (their set, weights, or bounds) change.
  watch(
    () => viewedList,
    () => scene.invalidate()
  );

  function createMosaic() {
    const b = stage?.bounds(true); // imageable extent (soft limits + ½ FOV) — matches the frame + paintable area
    const fov = instrument?.fov;
    if (!b || !fov) return;
    const m = inpaint.createFor({ x: b.minX, y: b.minY, w: b.maxX - b.minX, h: b.maxY - b.minY }, fov[0]);
    inpaint.view(m.id); // newest-touched, so it's already the active destination
  }

  async function combineSelected() {
    const c = await inpaint.combineMany(viewedList.map((m) => m.id));
    if (c) inpaint.view(c.id);
  }

  function rowClick(e: { metaKey: boolean; ctrlKey: boolean }, m: InpaintMosaic) {
    if (e.metaKey || e.ctrlKey) inpaint.toggleView(m.id);
    else if (inpaint.isViewed(m.id) && viewedList.length === 1) inpaint.view(null);
    else inpaint.view(m.id);
  }

  function eraseRegion(hit: EraseHit, channel?: string) {
    toastError(Promise.all(hit.mosaicIds.map((id) => inpaint.eraseFrom(id, hit.rect, channel))));
  }

  // The channel's identity color is baked onto the mosaic at paint time (see Inpainter.paintInto), so it
  // stays correct for stored mosaics regardless of the live preview / active profile.
  function channelColor(channel: string): string {
    for (const m of viewedList) {
      const c = m.channels[channel]?.color;
      if (c) return c;
    }
    return 'var(--color-fg-muted)';
  }

  const setWeight = useThrottle(
    (id: string, channel: string, weight: number) => inpaint.setChannelWeight(id, channel, weight),
    () => 80
  );
</script>

{#snippet moveTargets(m: InpaintMosaic)}
  {#each list as t (t.id)}
    {#if t.id !== m.id}
      <ContextMenu.Item onSelect={() => toastError(inpaint.flattenInto(m.id, t.id, { discardSource: true }))}>
        {t.name}
      </ContextMenu.Item>
    {/if}
  {/each}
{/snippet}

{#snippet mosaicMenu(m: InpaintMosaic)}
  {#if activeId !== m.id}
    <ContextMenu.Item onSelect={() => inpaint.makeActive(m.id)}>
      <Record width="14" height="14" />
      Paint here
    </ContextMenu.Item>
  {/if}
  {#if inpaint.isViewed(m.id) && viewedList.length > 1}
    <ContextMenu.Item onSelect={combineSelected}>
      <VectorCombine width="14" height="14" />
      Combine {viewedList.length} viewed
    </ContextMenu.Item>
  {/if}
  {#if list.length > 1}
    <ContextMenu.Sub>
      <ContextMenu.SubTrigger>
        <VectorCombine width="14" height="14" />
        Move into
      </ContextMenu.SubTrigger>
      <ContextMenu.SubContent class="min-w-40">
        {@render moveTargets(m)}
      </ContextMenu.SubContent>
    </ContextMenu.Sub>
  {/if}
  <ContextMenu.Separator />
  <ContextMenu.Item variant="destructive" onSelect={() => inpaint.delete(m.id)}>
    <TrashCanOutline width="14" height="14" />
    Delete
  </ContextMenu.Item>
{/snippet}

{#snippet eraseMenu(hit: EraseHit)}
  {#if hit.channels.length < 3}
    {#each hit.channels as channel (channel)}
      <ContextMenu.Item onSelect={() => eraseRegion(hit, channel)}>
        <span class="h-2 w-2 shrink-0 rounded-full" style:background-color={channelColor(channel)}></span>
        Erase {channel} here
      </ContextMenu.Item>
    {/each}
    {#if hit.channels.length > 1}
      <ContextMenu.Item onSelect={() => eraseRegion(hit)}>
        <Eraser width="14" height="14" />
        Erase all channels
      </ContextMenu.Item>
    {/if}
  {:else}
    <ContextMenu.Sub>
      <ContextMenu.SubTrigger>
        <Eraser width="14" height="14" />
        Erase inpaint
      </ContextMenu.SubTrigger>
      <ContextMenu.SubContent class="min-w-40">
        <ContextMenu.Item onSelect={() => eraseRegion(hit)}>
          <Eraser width="14" height="14" />
          All channels
        </ContextMenu.Item>
        <ContextMenu.Separator />
        {#each hit.channels as channel (channel)}
          <ContextMenu.Item onSelect={() => eraseRegion(hit, channel)}>
            <span class="h-2 w-2 shrink-0 rounded-full" style:background-color={channelColor(channel)}></span>
            {channel}
          </ContextMenu.Item>
        {/each}
      </ContextMenu.SubContent>
    </ContextMenu.Sub>
  {/if}
{/snippet}

<div class="flex flex-col gap-0.5">
  <div class="flex items-center gap-1 px-3 py-1">
    <span class="flex-1 text-base font-medium tracking-wide text-fg-muted/70 uppercase">Inpaint</span>
    <Button variant="ghost" size="icon-xs" title="New mosaic" onclick={createMosaic}>
      <Plus width="16" height="16" />
    </Button>
  </div>

  {#each list as m (m.id)}
    {@const isViewed = inpaint.isViewed(m.id)}
    {@const isActive = activeId === m.id}
    <div class={cn('mx-1.5 rounded-xs', isViewed && 'border-t border-border/60 bg-element-selected/40')}>
      <ContextMenu.Root>
        <ContextMenu.Trigger>
          {#snippet child({ props })}
            <div
              {...props}
              class="flex h-8 w-full cursor-pointer items-center gap-2 rounded-sm px-3 text-lg outline-none select-none hover:bg-element-hover"
              role="button"
              tabindex="0"
              onclick={(e) => rowClick(e, m)}
              onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && rowClick(e, m)}
            >
              <button
                type="button"
                class="shrink-0"
                title={isActive ? (recording ? 'Recording here' : 'Painting here') : 'Paint here'}
                onclick={(e) => {
                  e.stopPropagation();
                  inpaint.makeActive(m.id);
                }}
              >
                <Record
                  width="15"
                  height="15"
                  class={cn(
                    isActive ? 'text-danger' : 'text-fg-muted hover:text-fg',
                    isActive && recording && 'animate-pulse motion-reduce:animate-none'
                  )}
                />
              </button>
              <Rename
                value={m.name}
                size="sm"
                onSave={(v) => inpaint.rename(m.id, v)}
                class="min-w-0 flex-1"
                textClass="block cursor-pointer truncate {isViewed ? 'text-fg' : 'text-fg-muted'}"
              />
              <span class="shrink-0 rounded bg-element-bg px-1 text-base text-fg-muted tabular-nums">
                {Object.keys(m.channels).length}
              </span>
            </div>
          {/snippet}
        </ContextMenu.Trigger>
        <ContextMenu.Content class="min-w-44">
          {@render mosaicMenu(m)}
        </ContextMenu.Content>
      </ContextMenu.Root>
      {#if isViewed && viewedList.length === 1}
        <div class="rounded-xs border-y border-border/60 pb-2">
          {#each Object.entries(m.channels) as [channel, { weight }] (channel)}
            <div class="flex h-8 items-center gap-2 px-3.5">
              <span class="w-10 shrink-0 truncate text-base text-fg-muted">{channel}</span>
              <input
                type="range"
                class="thin-slider flex-1"
                min="0"
                max="1"
                step="0.01"
                value={weight}
                style:--thumb={channelColor(channel)}
                oninput={(e) => setWeight(m.id, channel, e.currentTarget.valueAsNumber)}
                onchange={(e) => {
                  setWeight.cancel();
                  inpaint.setChannelWeight(m.id, channel, e.currentTarget.valueAsNumber);
                }}
              />
            </div>
          {/each}
          {#if Object.keys(m.channels).length === 0}
            <p class="flex h-8 items-center px-3 text-base text-fg-faint">Paint here to add channels</p>
          {/if}
        </div>
      {/if}
    </div>
  {/each}
  {#if list.length === 0}
    <p class="px-1.5 py-2 text-center text-base text-fg-faint">No mosaics yet</p>
  {/if}
</div>

<style>
  /* Thin track + circular thumb (thumb tinted with the channel color via --thumb). */
  .thin-slider {
    height: 12px;
    cursor: pointer;
    appearance: none;
    background: transparent;
    --track-h: 2px;
    --thumb-d: 8px;
  }
  .thin-slider::-webkit-slider-runnable-track {
    height: var(--track-h);
    border-radius: 9999px;
    background: color-mix(in oklch, var(--color-fg-faint) 60%, transparent);
  }
  .thin-slider::-webkit-slider-thumb {
    appearance: none;
    width: var(--thumb-d);
    height: var(--thumb-d);
    margin-top: calc((var(--track-h) - var(--thumb-d)) / 2);
    border-radius: 9999px;
    background: var(--thumb, var(--color-fg-muted));
    box-shadow: 0 0 0 1px color-mix(in oklch, var(--color-fg-faint) 50%, transparent);
  }
  .thin-slider::-moz-range-track {
    height: var(--track-h);
    border-radius: 9999px;
    background: color-mix(in oklch, var(--color-fg-faint) 60%, transparent);
  }
  .thin-slider::-moz-range-thumb {
    width: var(--thumb-d);
    height: var(--thumb-d);
    border: none;
    border-radius: 9999px;
    background: var(--thumb, var(--color-fg-muted));
    box-shadow: 0 0 0 1px color-mix(in oklch, var(--color-fg-faint) 50%, transparent);
  }
</style>
