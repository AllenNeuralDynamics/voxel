<script lang="ts">
  import { watch } from 'runed';
  import { onMount } from 'svelte';
  import { SvelteMap, SvelteSet } from 'svelte/reactivity';

  import { Crosshair, FitToScreen, FolderMoveOutline, ImageAlbum, Layers, Plus, TrashCanOutline } from '$lib/icons';
  import { Button, ContextMenu, HoverCard, Rename } from '$lib/kit';
  import { getVoxelApp, type Instrument, type Snapshot, type SnapshotGroup } from '$lib/model';
  import { cn, toastError, trimFloat } from '$lib/utils';

  import type { Bounds, Painter } from '../draw';
  import { getStageScene, type StageLayer, useLayer } from '../scene.svelte';

  const app = getVoxelApp();
  const snaps = app.snaps;
  const scene = getStageScene();
  const stage = $derived(app.instrument?.stage ?? null);
  const instrument = $derived(app.instrument);

  const active = $derived(snaps.activeSnap);
  const tiles = $derived(active?.tiles ?? []);
  const mip = $derived(active?.group.mipEnabled ?? false);
  const activeGroupId = $derived(active?.group.id ?? null);
  const selected = $derived(active?.selected ?? null); // multi-selected snap ids in the shown group

  const groups = $derived(snaps.snapshotGroupList);
  const targetGroupId = $derived(snaps.targetGroupId);

  let isolated = $state<Snapshot | null>(null);
  let anchor: string | null = null; // range-select anchor
  let focusColor = '#e5e7eb';

  const ZTOL_UM = 0.5; // snapshots within this Z are treated as the same optical plane

  // ── Tile bitmaps: full-res blob (crisp) with the thumbnail as an instant placeholder ──
  const thumbs = new SvelteMap<string, HTMLImageElement>();
  const bitmaps = new SvelteMap<string, ImageBitmap>();
  const decoding = new SvelteSet<string>();

  function thumbFor(t: Snapshot): HTMLImageElement {
    let img = thumbs.get(t.id);
    if (!img) {
      img = new Image();
      img.onload = () => scene.invalidate();
      img.src = t.thumbnail;
      thumbs.set(t.id, img);
    }
    return img;
  }

  function bitmapFor(t: Snapshot): ImageBitmap | null {
    const existing = bitmaps.get(t.id);
    if (existing) return existing;
    if (!decoding.has(t.id)) {
      decoding.add(t.id);
      createImageBitmap(t.blob)
        .then((bmp) => {
          bitmaps.set(t.id, bmp);
          decoding.delete(t.id);
          scene.invalidate();
        })
        .catch(() => decoding.delete(t.id));
    }
    return null;
  }

  function pruneBitmaps(keep: Set<string>) {
    for (const [id, bmp] of bitmaps) {
      if (!keep.has(id)) {
        bmp.close();
        bitmaps.delete(id);
      }
    }
  }

  // Z-planes for MIP: group tiles within ZTOL of each other; newest paints last within a plane.
  const zPlanes = $derived.by<Snapshot[][]>(() => {
    const sorted = [...tiles].sort((a, b) => a.stageZ - b.stageZ);
    const planes: Snapshot[][] = [];
    for (const t of sorted) {
      const last = planes[planes.length - 1];
      if (last && Math.abs(t.stageZ - last[0].stageZ) <= ZTOL_UM) last.push(t);
      else planes.push([t]);
    }
    for (const pl of planes) pl.sort((a, b) => a.timestamp - b.timestamp);
    return planes;
  });

  function drawTile(p: Painter, t: Snapshot) {
    const img = bitmapFor(t) ?? thumbFor(t);
    if (img instanceof HTMLImageElement && (!img.complete || img.naturalWidth === 0)) return;
    p.image(img, t.stageX - t.fovW / 2, t.stageY - t.fovH / 2, t.fovW, t.fovH);
  }

  const draw = (p: Painter) => {
    if (mip) {
      // Z-aware max projection: source-over within a plane (latest wins), lighten across planes.
      p.pass('source-over', (acc) => {
        for (const plane of zPlanes) acc.pass('lighten', (planeP) => plane.forEach((t) => drawTile(planeP, t)));
      });
    } else {
      for (const t of [...tiles].sort((a, b) => a.timestamp - b.timestamp)) drawTile(p, t);
    }
    if (isolated) drawTile(p, isolated); // isolate: its pixels win on top
    const sel = selected;
    if (sel) {
      const d = p.px(1); // inset 1px/side so the outline clears the coincident FOV box drawn over it
      p.strokeStyle = focusColor;
      for (const t of tiles) {
        if (!sel.has(t.id)) continue;
        p.lineWidthPx = isolated?.id === t.id ? 2 : 1.5;
        p.strokeRect(t.stageX - t.fovW / 2 + d, t.stageY - t.fovH / 2 + d, t.fovW - 2 * d, t.fovH - 2 * d);
      }
    }
  };

  function hitTile(world: [number, number]): Snapshot | null {
    const [x, y] = world;
    for (let i = tiles.length - 1; i >= 0; i--) {
      const t = tiles[i];
      if (Math.abs(x - t.stageX) <= t.fovW / 2 && Math.abs(y - t.stageY) <= t.fovH / 2) return t;
    }
    return null;
  }

  const MAX_UPSCALE = 4; // don't upscale a tile's source pixels beyond this, or it turns blocky
  function tileMaxScale(): number | null {
    let nativePxPerUm = 0;
    for (const t of tiles) {
      const bmp = bitmaps.get(t.id);
      if (bmp && t.fovW > 0) nativePxPerUm = Math.max(nativePxPerUm, bmp.width / t.fovW);
    }
    return nativePxPerUm > 0 ? nativePxPerUm * MAX_UPSCALE : null;
  }

  const layer: StageLayer<Snapshot> = {
    id: 'snapshots',
    z: 0,
    get visible() {
      return activeGroupId !== null; // radio: the one selected group is shown, or none
    },
    draw,
    hitTest: hitTile,
    onSelect: (snap, e) => onCanvasSelect(snap, e),
    onActivate: (snap) => {
      snaps.select([snap.id]);
      isolated = snap;
    },
    menu: tileMenu,
    maxScale: tileMaxScale
  };
  useLayer(layer);

  function goToSnap(snap: Snapshot) {
    toastError(stage?.moveTo({ x: snap.stageX, y: snap.stageY, z: snap.stageZ }));
  }

  // A menu action targets the whole selection when the clicked snap is part of it, else just that snap.
  function menuTargets(snap: Snapshot): string[] {
    const sel = selected;
    return sel && sel.size > 0 && sel.has(snap.id) ? [...sel] : [snap.id];
  }

  // Union of the tiles' FOV footprints (µm), or null when the set is empty.
  function tilesBounds(ids: string[]): Bounds | null {
    const want = new Set(ids);
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const t of tiles) {
      if (!want.has(t.id)) continue;
      minX = Math.min(minX, t.stageX - t.fovW / 2);
      maxX = Math.max(maxX, t.stageX + t.fovW / 2);
      minY = Math.min(minY, t.stageY - t.fovH / 2);
      maxY = Math.max(maxY, t.stageY + t.fovH / 2);
    }
    return minX <= maxX ? { minX, minY, maxX, maxY } : null;
  }

  // Frame the given tiles in the canvas viewport (a touch of extra padding around the footprint).
  function fitTiles(ids: string[]) {
    const b = tilesBounds(ids);
    if (b) scene.requestView(b, 0.7);
  }

  function moveToNewGroup(ids: string[]) {
    snaps.moveToSnapshotGroup(ids, snaps.createSnapshotGroup().id);
  }

  function zRange(gTiles: Snapshot[]): string {
    let lo = Infinity;
    let hi = -Infinity;
    for (const t of gTiles) {
      lo = Math.min(lo, t.stageZ);
      hi = Math.max(hi, t.stageZ);
    }
    const l = Math.round(lo);
    const h = Math.round(hi);
    return l === h ? `${l} µm` : `${l} – ${h} µm`;
  }

  // Distinct channels across a group's tiles, each with its resolved colormap color.
  function groupChannels(gTiles: Snapshot[]): { label: string; color: string }[] {
    const seen: Record<string, string> = {};
    for (const t of gTiles) {
      for (const ch of Object.values(t.channels)) {
        if (!(ch.label in seen)) seen[ch.label] = instrument?.preview.resolveColor(ch.colormap) ?? 'var(--color-fg-muted)';
      }
    }
    return Object.entries(seen).map(([label, color]) => ({ label, color }));
  }

  // Canvas tile click: plain = select one, ⌘/Ctrl = toggle, Shift = add. (No range: tiles have no linear order.)
  function onCanvasSelect(snap: Snapshot, e?: PointerEvent) {
    if (e?.metaKey || e?.ctrlKey) snaps.toggleSelect(snap.id);
    else if (e?.shiftKey) snaps.addSelect(snap.id);
    else snaps.select([snap.id]);
    anchor = snap.id; // keep the sidebar's range anchor in sync with the last canvas pick
  }

  // Sidebar snap click: plain = select one, ⌘/Ctrl = toggle, Shift = range from the anchor.
  function onSnapClick(e: MouseEvent | KeyboardEvent, snap: Snapshot) {
    const order = tiles.map((t) => t.id);
    if (e.shiftKey && anchor) {
      const a = order.indexOf(anchor);
      const b = order.indexOf(snap.id);
      if (a !== -1 && b !== -1) {
        const [lo, hi] = a < b ? [a, b] : [b, a];
        snaps.select(order.slice(lo, hi + 1));
      }
    } else if (e.metaKey || e.ctrlKey) {
      snaps.toggleSelect(snap.id);
      anchor = snap.id;
    } else {
      snaps.select([snap.id]);
      anchor = snap.id;
    }
    scene.invalidate();
  }

  // Prune decoded frames + redraw when the drawable content changes.
  watch(
    () => [tiles, mip] as const,
    () => {
      pruneBitmaps(new Set(tiles.map((t) => t.id)));
      scene.invalidate();
    }
  );
  // Isolation is per-viewed-group; drop it when the group changes.
  watch(
    () => activeGroupId,
    () => {
      isolated = null;
    }
  );

  onMount(() => {
    focusColor = getComputedStyle(document.documentElement).getPropertyValue('--color-primary').trim() || focusColor;
  });
</script>

{#snippet snapshotInfoCard(snap: Snapshot, inst: Instrument)}
  <div class="flex flex-col divide-y divide-border/50 text-xs">
    <div class="flex flex-col gap-1 px-2.5 py-2">
      <div class="flex items-center justify-between gap-2">
        <span class="min-w-0 truncate font-medium text-fg">{snap.label}</span>
        {#if snap.profileLabel}
          <span class="shrink-0 rounded bg-element-bg px-1.5 py-0.5 text-fg-muted">{snap.profileLabel}</span>
        {/if}
      </div>
      <div class="grid grid-cols-3 gap-2 pt-0.5 font-mono tabular-nums">
        <div class="flex flex-col">
          <span class="text-fg-faint">X</span>
          <span class="text-fg">{Math.round(snap.stageX)}</span>
        </div>
        <div class="flex flex-col">
          <span class="text-fg-faint">Y</span>
          <span class="text-fg">{Math.round(snap.stageY)}</span>
        </div>
        <div class="flex flex-col">
          <span class="text-fg-faint">Z</span>
          <span class="text-fg">{Math.round(snap.stageZ)}</span>
        </div>
      </div>
    </div>

    {#each Object.entries(snap.channels) as [name, ch] (name)}
      {@const color = inst.preview.resolveColor(ch.colormap) ?? 'var(--color-fg-muted)'}
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
            <dd class="text-right text-fg tabular-nums">{trimFloat(ch.detection.exposureTime, 2)} ms</dd>
          {/if}
          {#if ch.detection?.binning != null}
            <dt class="text-fg-muted">Binning</dt>
            <dd class="text-right text-fg tabular-nums">{ch.detection.binning}×</dd>
          {/if}
          {#if ch.illumination?.powerSetpoint != null}
            <dt class="text-fg-muted">Power</dt>
            <dd class="text-right text-fg tabular-nums">{trimFloat(ch.illumination.powerSetpoint, 1)} mW</dd>
          {/if}
        </dl>
      </div>
    {/each}
  </div>
{/snippet}

{#snippet groupInfoCard(g: SnapshotGroup)}
  {@const gTiles = snaps.tilesOf(g.id)}
  {@const channels = groupChannels(gTiles)}
  <div class="flex flex-col divide-y divide-border/50 text-xs">
    <div class="flex min-h-8 items-center justify-between gap-2 px-2.5 py-2">
      <span class="min-w-0 truncate font-medium text-fg">{g.name}</span>
      {#if targetGroupId === g.id}
        <span class="shrink-0 rounded bg-element-bg px-1.5 py-0.5 text-fg-muted">target</span>
      {/if}
    </div>
    <dl class="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 px-2.5 py-2">
      <dt class="text-fg-muted">Tiles</dt>
      <dd class="text-right text-fg tabular-nums">{gTiles.length}</dd>
      {#if gTiles.length > 0}
        <dt class="text-fg-muted">Z range</dt>
        <dd class="text-right text-fg tabular-nums">{zRange(gTiles)}</dd>
      {/if}
      <dt class="text-fg-muted">Max projection</dt>
      <dd class="text-right text-fg">{g.mipEnabled ? 'on' : 'off'}</dd>
    </dl>
    {#if channels.length > 0}
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1 px-2.5 py-2">
        {#each channels as ch (ch.label)}
          <span class="flex items-center gap-1.5">
            <span class="h-2 w-2 shrink-0 rounded-full" style:background-color={ch.color}></span>
            <span class="text-fg">{ch.label}</span>
          </span>
        {/each}
      </div>
    {/if}
  </div>
{/snippet}

{#snippet tileMenu(snap: Snapshot)}
  {@const ids = menuTargets(snap)}
  {@const many = ids.length > 1}
  <ContextMenu.Item onSelect={() => goToSnap(snap)}>
    <Crosshair width="14" height="14" />
    Go to snapshot
  </ContextMenu.Item>
  <ContextMenu.Item onSelect={() => fitTiles(ids)}>
    <FitToScreen width="14" height="14" />
    {many ? `Recenter ${ids.length} selected` : 'Recenter'}
  </ContextMenu.Item>
  <ContextMenu.Sub>
    <ContextMenu.SubTrigger>
      <FolderMoveOutline width="14" height="14" />
      Move to
    </ContextMenu.SubTrigger>
    <ContextMenu.SubContent class="min-w-40">
      {#each groups as g (g.id)}
        {#if g.id !== activeGroupId}
          <ContextMenu.Item onSelect={() => snaps.moveToSnapshotGroup(ids, g.id)}>
            <ImageAlbum width="14" height="14" />
            {g.name}
          </ContextMenu.Item>
        {/if}
      {/each}
      <ContextMenu.Separator />
      <ContextMenu.Item onSelect={() => moveToNewGroup(ids)}>
        <Plus width="14" height="14" />
        New group
      </ContextMenu.Item>
    </ContextMenu.SubContent>
  </ContextMenu.Sub>
  <ContextMenu.Separator />
  <ContextMenu.Item variant="destructive" onSelect={() => snaps.remove(ids)}>
    <TrashCanOutline width="14" height="14" />
    {many ? `Delete ${ids.length} snapshots` : 'Delete'}
  </ContextMenu.Item>
{/snippet}

{#snippet snapRow(snap: Snapshot)}
  {@const isSelected = selected?.has(snap.id) ?? false}
  <ContextMenu.Root>
    <ContextMenu.Trigger>
      {#snippet child({ props: ctxProps })}
        <HoverCard.Root openDelay={550} closeDelay={120}>
          <HoverCard.Trigger {...ctxProps}>
            {#snippet child({ props })}
              <div
                {...props}
                class={cn(
                  'flex w-full cursor-pointer items-center gap-2 rounded-sm py-1 pr-2 pl-7 text-sm outline-none select-none',
                  isSelected ? 'bg-element-selected' : 'hover:bg-element-hover'
                )}
                role="button"
                tabindex="0"
                onclick={(e) => onSnapClick(e, snap)}
                onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && onSnapClick(e, snap)}
              >
                <img src={snap.thumbnail} alt="" class="h-6 w-8 shrink-0 rounded-sm border border-border object-cover" />
                <Rename
                  value={snap.label}
                  size="sm"
                  onSave={(v) => snaps.rename(snap.id, v)}
                  class="min-w-0 flex-1"
                  textClass="block cursor-pointer truncate {isSelected ? 'text-fg' : 'text-fg-muted'}"
                />
                <span class="shrink-0 font-mono text-xs text-fg-faint tabular-nums">z{Math.round(snap.stageZ)}</span>
              </div>
            {/snippet}
          </HoverCard.Trigger>
          {#if instrument}
            <HoverCard.Content class="w-60" side="right" sideOffset={12} align="start">
              {@render snapshotInfoCard(snap, instrument)}
            </HoverCard.Content>
          {/if}
        </HoverCard.Root>
      {/snippet}
    </ContextMenu.Trigger>
    <ContextMenu.Content class="min-w-44">
      {@render tileMenu(snap)}
    </ContextMenu.Content>
  </ContextMenu.Root>
{/snippet}

<div class="flex flex-col gap-0.5">
  <div class="flex items-center gap-1 px-2 py-1">
    <span class="flex-1 text-xs font-medium tracking-wide text-fg-muted/70 uppercase">Snapshots</span>
    <Button variant="ghost" size="icon-xs" title="New group" onclick={() => snaps.createSnapshotGroup()}>
      <Plus width="16" height="16" />
    </Button>
  </div>

  {#each groups as g (g.id)}
    {@const isTarget = targetGroupId === g.id}
    {@const count = snaps.tilesOf(g.id).length}
    {@const isActive = activeGroupId === g.id}
    <div class={cn('rounded-md', isActive && 'bg-element-selected/40')}>
      <ContextMenu.Root>
        <ContextMenu.Trigger>
        {#snippet child({ props: ctxProps })}
          <HoverCard.Root openDelay={550} closeDelay={120}>
            <HoverCard.Trigger {...ctxProps}>
              {#snippet child({ props })}
                <div
                  {...props}
                  class={cn(
                    'group flex w-full cursor-pointer items-center gap-2 rounded-sm px-2.5 py-1 text-sm outline-none select-none',
                    'hover:bg-element-hover'
                  )}
                  role="button"
                  tabindex="0"
                  onclick={() => snaps.viewGroup(activeGroupId === g.id ? null : g.id)}
                  onkeydown={(e) =>
                    (e.key === 'Enter' || e.key === ' ') && snaps.viewGroup(activeGroupId === g.id ? null : g.id)}
                >
                  <button
                    type="button"
                    class="shrink-0"
                    title={isTarget ? 'Capture target' : 'Set as capture target'}
                    onclick={(e) => {
                      e.stopPropagation();
                      snaps.setTarget(g.id);
                      snaps.viewGroup(g.id);
                    }}
                  >
                    <ImageAlbum width="15" height="15" class={isTarget ? 'text-primary' : 'text-fg-muted hover:text-fg'} />
                  </button>
                  <Rename
                    value={g.name}
                    size="sm"
                    onSave={(v) => snaps.renameSnapshotGroup(g.id, v)}
                    class="min-w-0 flex-1"
                    textClass="block cursor-pointer truncate {isTarget || isActive ? 'text-fg' : ''}"
                  />
                  <span class="shrink-0 rounded bg-element-bg px-1 text-xs text-fg-muted tabular-nums">{count}</span>
                </div>
              {/snippet}
            </HoverCard.Trigger>
            <HoverCard.Content class="w-60" side="right" sideOffset={12} align="start">
              {@render groupInfoCard(g)}
            </HoverCard.Content>
          </HoverCard.Root>
        {/snippet}
      </ContextMenu.Trigger>
      <ContextMenu.Content class="min-w-44">
        <ContextMenu.Item onSelect={() => snaps.setTarget(g.id)}>
          <ImageAlbum width="14" height="14" />
          Set as target
        </ContextMenu.Item>
        <ContextMenu.Item onSelect={() => snaps.setSnapshotGroupMip(g.id, !g.mipEnabled)}>
          <Layers width="14" height="14" />
          {g.mipEnabled ? 'Max projection on' : 'Max projection off'}
        </ContextMenu.Item>
        <ContextMenu.Separator />
        <ContextMenu.Item variant="destructive" onSelect={() => snaps.deleteSnapshotGroup(g.id)}>
          <TrashCanOutline width="14" height="14" />
          Delete group
        </ContextMenu.Item>
      </ContextMenu.Content>
      </ContextMenu.Root>
      {#if activeGroupId === g.id}
        {#each snaps.tilesOf(g.id) as tile (tile.id)}
          {@render snapRow(tile)}
        {/each}
      {/if}
    </div>
  {/each}
  {#if groups.length === 0}
    <p class="px-1.5 py-2 text-center text-xs text-fg-faint">No snapshots yet</p>
  {/if}
</div>
