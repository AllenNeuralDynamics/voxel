<script lang="ts">
  import { type DragDropState, draggable, droppable } from '@thisux/sveltednd';
  import { watch } from 'runed';
  import { onMount, tick } from 'svelte';
  import { SvelteMap, SvelteSet } from 'svelte/reactivity';
  import { slide } from 'svelte/transition';

  import {
    CenterFocus,
    ChevronDown,
    ChevronRight,
    Crosshair,
    FitToScreen,
    Folder,
    FolderMoveOutline,
    FolderOpenOutline,
    Layers,
    PanelLeft,
    PencilOutline,
    Plus,
    TrashCanOutline
  } from '$lib/icons';
  import { Button, ContextMenu, Rename } from '$lib/kit';
  import {
    DEFAULT_STAGE_ORIENTATION,
    getVoxelApp,
    type Snapshot,
    type SnapshotGroup,
    wheelZoomFactor
  } from '$lib/model';
  import { cn, pref, toastError, trimFloat } from '$lib/utils';

  import LiveThumbnail from './LiveThumbnail.svelte';

  const app = getVoxelApp();
  const snaps = app.snaps;
  const instrument = $derived(app.instrument);

  // Live feed (when a preview is running) — shown as a corner glimpse while browsing snaps.
  const livePreview = $derived.by(() => {
    const p = app.instrument?.preview;
    return p?.isPreviewing ? p : null;
  });

  // Snapshot picker: dock open/closed state persists across sessions.
  const sidebarOpen = pref('snaps:sidebar-open', true);

  // ── Snapshot picker (sidebar tree) ──
  const groups = $derived(snaps.snapshotGroupList);
  const targetGroupId = $derived(snaps.targetGroupId); // folder new captures land in (most-recently touched)

  // The viewed group highlights its folder row; the focused tile within it highlights its own row.
  const activeSnapId = $derived(snaps.activeSnap?.focused?.id ?? null);
  const activeGroupId = $derived(snaps.activeSnap?.group.id ?? null);

  // Selection holds a mix of snapshot and group ids (disambiguated by the groups map).
  const selected = new SvelteSet<string>();
  let anchor = $state<string | null>(null);
  const collapsed = new SvelteSet<string>(); // groups whose children are hidden

  let renamingId = $state<string | null>(null);
  let renameValue = $state('');

  const isGroupId = (id: string) => snaps.snapshotGroups.has(id);
  const selGroups = $derived([...selected].filter(isGroupId));
  const selSnaps = $derived([...selected].filter((id) => !isGroupId(id)));

  // Flat top-to-bottom order of selectable rows, for shift-range selection.
  const visibleOrder = $derived.by<string[]>(() => {
    const order: string[] = [];
    for (const g of groups) {
      order.push(g.id);
      if (!collapsed.has(g.id)) for (const t of snaps.tilesOf(g.id)) order.push(t.id);
    }
    return order;
  });

  function pick(id: string) {
    if (isGroupId(id)) {
      snaps.viewGroup(id);
    } else {
      const snap = snaps.items.get(id);
      if (snap) snaps.viewInGroup(snap.groupId, id); // open its group, focused on it
    }
  }

  function onRowClick(e: MouseEvent | KeyboardEvent, id: string) {
    if (e.shiftKey && anchor) {
      const order = visibleOrder;
      const a = order.indexOf(anchor);
      const b = order.indexOf(id);
      if (a !== -1 && b !== -1) {
        selected.clear();
        const [lo, hi] = a < b ? [a, b] : [b, a];
        for (let i = lo; i <= hi; i++) selected.add(order[i]);
      }
    } else if (e.metaKey || e.ctrlKey) {
      if (selected.has(id)) selected.delete(id);
      else selected.add(id);
      anchor = id;
    } else {
      selected.clear();
      selected.add(id);
      anchor = id;
      pick(id);
    }
  }

  function toggleCollapse(id: string) {
    if (collapsed.has(id)) collapsed.delete(id);
    else collapsed.add(id);
  }

  // The canvas context menu targets a snapshot (right-clicked tile) or a bare stage position
  // (right-clicked empty space within the frame). Rows carry their own snap directly.
  type CanvasTarget = { kind: 'snap'; snap: Snapshot } | { kind: 'pos'; x: number; y: number };
  let menuTarget = $state<CanvasTarget | null>(null);

  function goToSnap(snap: Snapshot) {
    toastError(instrument?.stage.moveTo({ x: snap.stageX, y: snap.stageY, z: snap.stageZ }));
  }

  // Move the stage to an exact clicked position (z unchanged), clamped to the reachable stage limits.
  function goToPos(x: number, y: number) {
    const b = stageBounds;
    let gx = x;
    let gy = y;
    if (b && fov) {
      gx = Math.min(Math.max(x, b.minX + fov[0] / 2), b.maxX - fov[0] / 2);
      gy = Math.min(Math.max(y, b.minY + fov[1] / 2), b.maxY - fov[1] / 2);
    }
    const z = app.instrument?.stage.z.position?.value ?? 0;
    toastError(instrument?.stage.moveTo({ x: gx, y: gy, z }));
  }

  /** Right-click on the canvas: a tile, or the clicked position when inside the stage frame; else no menu. */
  function handleCanvasContext(e: MouseEvent) {
    const hit = hitTile(e.clientX, e.clientY);
    if (hit) {
      menuTarget = { kind: 'snap', snap: hit };
      pick(hit.id); // focus the right-clicked tile
      return;
    }
    const b = stageBounds;
    if (b) {
      const rect = canvasEl.getBoundingClientRect();
      const sx = pxToSx(e.clientX - rect.left);
      const sy = pyToSy(e.clientY - rect.top);
      if (sx >= b.minX && sx <= b.maxX && sy >= b.minY && sy <= b.maxY) {
        menuTarget = { kind: 'pos', x: sx, y: sy };
        return; // empty space within the frame → offer "go to position"
      }
    }
    e.preventDefault();
    e.stopPropagation(); // outside the frame (or none) → don't open a menu
    menuTarget = null;
  }

  function newGroup() {
    const g = snaps.createSnapshotGroup();
    startRename(g.id, g.name);
  }

  function startRename(id: string, current: string) {
    renamingId = id;
    renameValue = current;
  }

  function commitRename() {
    if (renamingId) snaps.renameSnapshotGroup(renamingId, renameValue.trim() || 'Untitled');
    renamingId = null;
  }

  function renameKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') commitRename();
    else if (e.key === 'Escape') renamingId = null;
  }

  function deleteSelection() {
    for (const gid of selGroups) snaps.deleteSnapshotGroup(gid); // cascades to the group's snapshots
    snaps.remove(selSnaps.filter((id) => snaps.items.has(id))); // some may already be gone with a group
    selected.clear();
  }

  // Menu delete: the whole selection when the target is part of a multi-selection, otherwise just the target.
  function menuDelete(snap: Snapshot) {
    if (selected.has(snap.id) && selected.size > 1) deleteSelection();
    else snaps.remove(snap.id);
  }

  function dragIds(id: string): string[] {
    // Dragging a selected snapshot carries the whole snapshot selection; otherwise just this one.
    return selected.has(id) && selSnaps.length > 0 ? selSnaps : [id];
  }

  function handleDrop(state: DragDropState<unknown>, target: string) {
    // The library delivers the dropped payload as `unknown`; our draggables always set `{ ids }`.
    const ids = (state.draggedItem as { ids?: string[] } | undefined)?.ids ?? [];
    if (ids.length) snaps.moveToSnapshotGroup(ids, target);
  }

  const rowBase = 'group flex w-full items-center gap-2 rounded-sm px-1.5 py-1 text-lg outline-none select-none';

  // What's being shown: the viewed folder (0..N tiles), from the store. Null when nothing is viewed.
  const active = $derived(snaps.activeSnap);
  const group = $derived(active?.group ?? null);
  const tiles = $derived(active?.tiles ?? []);
  const isGroup = $derived(group !== null);
  const mip = $derived(group?.mipEnabled ?? false);

  // Focus = the tile whose metadata shows (store-owned). Isolate = its pixels win (drawn opaque on top).
  const focused = $derived(active?.focused ?? null);
  let isolated = $state<Snapshot | null>(null);

  // Changes when the viewed folder switches — resets isolate + auto-fit.
  const viewKey = $derived(group?.id ?? null);

  // Live stage position + FOV drive the "you are here" marker; absolute stage µm, matching tile centers.
  const hereX = $derived(app.instrument?.stage.x.position?.value ?? null);
  const hereY = $derived(app.instrument?.stage.y.position?.value ?? null);
  const fov = $derived(app.instrument?.fov ?? null);

  // ── Viewport: stage-space center (µm) + uniform scale (CSS px per µm) ──
  let cx = $state(0);
  let cy = $state(0);
  let scale = $state(1);
  let userAdjusted = $state(false); // once the user pans/zooms, stop auto-fitting

  const MIN_SCALE = 1e-4;
  const MAX_SCALE = 200;

  let containerEl: HTMLDivElement;
  let canvasEl: HTMLCanvasElement;
  let ctx: CanvasRenderingContext2D | null = null;
  let markerColor = '#22c55e';
  let focusColor = '#e5e7eb';
  let boundsColor = '#3f3f46';

  // Live container size, measured from the DOM each frame (see syncSize).
  let viewW = $state(0);
  let viewH = $state(0);

  // Per-axis display sign (shared with the stage cube). Canonical is X-right, Y-up (matching the cube);
  // each sign flips its axis. stage µm ↔ canvas CSS px go through these four helpers so the sign lives
  // in one place. (Position-only: images draw upright, so a flip repositions tiles without mirroring them.)
  const orient = $derived(app.instrument?.stage.orientation ?? DEFAULT_STAGE_ORIENTATION);
  const sxToPx = (sx: number) => viewW / 2 + orient.x * (sx - cx) * scale;
  const syToPx = (sy: number) => viewH / 2 - orient.y * (sy - cy) * scale;
  const pxToSx = (px: number) => cx + orient.x * ((px - viewW / 2) / scale);
  const pyToSy = (py: number) => cy - orient.y * ((py - viewH / 2) / scale);

  // Imageable stage extent: stage position limits expanded by half a FOV on every side (the FOV is
  // centred on the stage, so imaging reaches half a frame past each limit — matching the grid view).
  const stageBounds = $derived.by(() => {
    const st = app.instrument?.stage;
    const xl = st?.x?.lowerLimit?.value;
    const xu = st?.x?.upperLimit?.value;
    const yl = st?.y?.lowerLimit?.value;
    const yu = st?.y?.upperLimit?.value;
    if (xl == null || xu == null || yl == null || yu == null || !fov) return null;
    const [fw, fh] = fov;
    return { minX: xl - fw / 2, maxX: xu + fw / 2, minY: yl - fh / 2, maxY: yu + fh / 2 };
  });

  // Zoom-out floor: can't shrink past the imageable stage fitting the canvas, with a little margin
  // so the frame doesn't sit flush against the edges at full zoom-out.
  const BOUNDS_FIT_MARGIN = 0.9;
  const minScale = $derived.by(() => {
    const b = stageBounds;
    if (!b || viewW <= 0 || viewH <= 0) return MIN_SCALE;
    const bw = b.maxX - b.minX;
    const bh = b.maxY - b.minY;
    if (bw <= 0 || bh <= 0) return MIN_SCALE;
    return Math.max(MIN_SCALE, Math.min(viewW / bw, viewH / bh) * BOUNDS_FIT_MARGIN);
  });

  // ── Tile images: full-res blob (crisp) with the thumbnail as an instant placeholder ──
  const thumbs = new SvelteMap<string, HTMLImageElement>();
  const bitmaps = new SvelteMap<string, ImageBitmap>();
  const decoding = new SvelteSet<string>();

  // Zoom-in ceiling: don't upscale a tile's source pixels beyond this, or it turns to blocks.
  const MAX_UPSCALE = 4;
  const maxScale = $derived.by(() => {
    let nativePxPerUm = 0;
    for (const t of tiles) {
      const bmp = bitmaps.get(t.id);
      if (bmp && t.fovW > 0) nativePxPerUm = Math.max(nativePxPerUm, bmp.width / t.fovW);
    }
    return nativePxPerUm > 0 ? nativePxPerUm * MAX_UPSCALE : MAX_SCALE;
  });

  function thumbFor(tile: Snapshot): HTMLImageElement {
    let img = thumbs.get(tile.id);
    if (!img) {
      img = new Image();
      img.onload = () => {
        needsRedraw = true;
      };
      img.src = tile.thumbnail;
      thumbs.set(tile.id, img);
    }
    return img;
  }

  /** Full-resolution frame decoded from the stored blob; null until ready (the thumbnail shows meanwhile). */
  function bitmapFor(tile: Snapshot): ImageBitmap | null {
    const existing = bitmaps.get(tile.id);
    if (existing) return existing;
    if (!decoding.has(tile.id)) {
      decoding.add(tile.id);
      createImageBitmap(tile.blob)
        .then((bmp) => {
          bitmaps.set(tile.id, bmp);
          decoding.delete(tile.id);
          needsRedraw = true;
        })
        .catch(() => decoding.delete(tile.id));
    }
    return null;
  }

  /** Release decoded frames for tiles no longer shown. */
  function pruneBitmaps(keep: Set<string>) {
    for (const [id, bmp] of bitmaps) {
      if (!keep.has(id)) {
        bmp.close();
        bitmaps.delete(id);
      }
    }
  }

  // Keep the viewport within the stage frame: clamp a center so the visible span stays inside [lo, hi],
  // or centers on the frame when the view is wider than it (zoomed out past the frame).
  // How far a stage edge may pan inward from the viewport border, as a fraction of the viewport width
  // (0 = edge stops flush at the border; 1/2 = edge can reach the viewport center).
  const EDGE_SLACK = 1 / 3;

  function clampAxis(c: number, halfView: number, lo: number, hi: number): number {
    if (halfView * 2 >= hi - lo) return (lo + hi) / 2; // whole axis fits → lock to center (no slack)
    const margin = halfView * (1 - 2 * EDGE_SLACK); // relax the flush clamp so an edge can pan toward center
    return Math.min(Math.max(c, lo + margin), hi - margin);
  }

  // Don't pan into empty space past the stage frame (no clamp until stage limits + FOV are known).
  function clampPan() {
    const b = stageBounds;
    if (!b || scale <= 0) return;
    cx = clampAxis(cx, viewW / (2 * scale), b.minX, b.maxX);
    cy = clampAxis(cy, viewH / (2 * scale), b.minY, b.maxY);
  }

  // Center + zoom the view to frame a stage-space box (µm) with a small margin.
  function frameBox(minX: number, minY: number, maxX: number, maxY: number) {
    const cw = viewW;
    const ch = viewH;
    const bw = maxX - minX;
    const bh = maxY - minY;
    if (cw <= 0 || ch <= 0 || bw <= 0 || bh <= 0) return;
    cx = (minX + maxX) / 2;
    cy = (minY + maxY) / 2;
    scale = Math.max(minScale, Math.min(cw / bw, ch / bh) * 0.9);
    clampPan();
  }

  // Frame a set of tiles' bounding box.
  function recenterToContent(items: Snapshot[]) {
    if (items.length === 0) return;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const t of items) {
      minX = Math.min(minX, t.stageX - t.fovW / 2);
      maxX = Math.max(maxX, t.stageX + t.fovW / 2);
      minY = Math.min(minY, t.stageY - t.fovH / 2);
      maxY = Math.max(maxY, t.stageY + t.fovH / 2);
    }
    frameBox(minX, minY, maxX, maxY);
  }

  // Auto-fit: frame the shown tiles, or the whole stage frame when there are no snapshots.
  function fitToContent() {
    if (tiles.length > 0) recenterToContent(tiles);
    else if (stageBounds) frameBox(stageBounds.minX, stageBounds.minY, stageBounds.maxX, stageBounds.maxY);
  }

  // "Fit all" button: frame everything and return to the auto-fit baseline (resume tracking new snaps).
  function fitAll() {
    userAdjusted = false;
    fitToContent();
  }

  // Whether every tile sits fully inside the current viewport (stage-space). Used to reframe a new
  // snapshot only when it lands out of view, instead of on every capture.
  function tilesInView(): boolean {
    if (viewW <= 0 || viewH <= 0 || scale <= 0) return true; // not measured yet — don't fight it
    const halfW = viewW / (2 * scale);
    const halfH = viewH / (2 * scale);
    return tiles.every(
      (t) =>
        t.stageX - t.fovW / 2 >= cx - halfW &&
        t.stageX + t.fovW / 2 <= cx + halfW &&
        t.stageY - t.fovH / 2 >= cy - halfH &&
        t.stageY + t.fovH / 2 <= cy + halfH
    );
  }

  // Recenter menu action: zoom to focus the selection (when the target is part of a multi-selection),
  // else just the target. Switch views first if it isn't currently shown.
  function recenterOn(snap: Snapshot) {
    if (!tiles.some((t) => t.id === snap.id)) {
      pick(snap.id); // not in the current view → switch to it, then frame once the view settles
      tick().then(() => {
        recenterToContent([snap]);
        userAdjusted = true;
      });
      return;
    }
    const targets = selected.has(snap.id) && selected.size > 1 ? tiles.filter((t) => selected.has(t.id)) : [snap];
    snaps.focus(snap.id);
    recenterToContent(targets);
    userAdjusted = true;
  }

  // ── Rendering ──
  let needsRedraw = false;
  let rendering = false;
  let animId: number | null = null;

  const ZTOL_UM = 0.5; // snapshots within this Z are treated as the same optical plane
  const scratch = document.createElement('canvas');
  const sctx = scratch.getContext('2d');

  // Group tiles into Z-planes: same-Z tiles form one plane (latest wins); distinct planes max-project.
  const zPlanes = $derived.by<Snapshot[][]>(() => {
    const sorted = [...tiles].sort((a, b) => a.stageZ - b.stageZ);
    const planes: Snapshot[][] = [];
    for (const t of sorted) {
      const last = planes[planes.length - 1];
      if (last && Math.abs(t.stageZ - last[0].stageZ) <= ZTOL_UM) last.push(t);
      else planes.push([t]);
    }
    for (const p of planes) p.sort((a, b) => a.timestamp - b.timestamp); // newest paints last
    return planes;
  });

  function drawTile(c: CanvasRenderingContext2D, t: Snapshot) {
    const img: ImageBitmap | HTMLImageElement | null = bitmapFor(t) ?? thumbFor(t);
    if (img instanceof HTMLImageElement && (!img.complete || img.naturalWidth === 0)) return;
    const left = sxToPx(t.stageX) - (t.fovW * scale) / 2;
    const top = syToPx(t.stageY) - (t.fovH * scale) / 2;
    c.drawImage(img, left, top, t.fovW * scale, t.fovH * scale);
  }

  function draw() {
    if (!ctx || !canvasEl) return;
    const dpr = devicePixelRatio;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, canvasEl.width, canvasEl.height);

    if (isGroup && mip) {
      drawMip(dpr);
    } else {
      // Single snap, or MIP off: one pass, newest last — latest wins everywhere.
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.imageSmoothingQuality = 'high';
      ctx.globalCompositeOperation = 'source-over';
      for (const t of [...tiles].sort((a, b) => a.timestamp - b.timestamp)) drawTile(ctx, t);
    }

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.globalCompositeOperation = 'source-over';
    ctx.imageSmoothingQuality = 'high';
    if (stageBounds) drawBounds(stageBounds);
    if (isolated) drawTile(ctx, isolated); // isolate: focused tile's pixels win on top
    if (focused) drawOutline(focused);
    if (hereX != null && hereY != null && fov) drawHere(hereX, hereY, fov[0], fov[1]);
  }

  // The imageable stage extent as a frame (stage limits + half-FOV buffer).
  function drawBounds(b: { minX: number; minY: number; maxX: number; maxY: number }) {
    if (!ctx) return;
    const left = Math.min(sxToPx(b.minX), sxToPx(b.maxX));
    const top = Math.min(syToPx(b.minY), syToPx(b.maxY));
    ctx.strokeStyle = boundsColor;
    ctx.lineWidth = 1;
    ctx.strokeRect(left, top, (b.maxX - b.minX) * scale, (b.maxY - b.minY) * scale);
  }

  /**
   * Z-aware max projection: composite each Z-plane's tiles latest-wins (so re-snaps of the same plane
   * don't double-brighten), then combine the planes with `lighten` so only different depths accumulate.
   */
  function drawMip(dpr: number) {
    if (!ctx || !sctx) return;
    if (scratch.width !== canvasEl.width || scratch.height !== canvasEl.height) {
      scratch.width = canvasEl.width;
      scratch.height = canvasEl.height;
    }
    let first = true;
    for (const plane of zPlanes) {
      sctx.setTransform(1, 0, 0, 1, 0, 0);
      sctx.clearRect(0, 0, scratch.width, scratch.height);
      sctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      sctx.imageSmoothingQuality = 'high';
      sctx.globalCompositeOperation = 'source-over';
      for (const t of plane) drawTile(sctx, t);

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.globalCompositeOperation = first ? 'source-over' : 'lighten';
      ctx.drawImage(scratch, 0, 0);
      first = false;
    }
  }

  function drawOutline(t: Snapshot) {
    if (!ctx) return;
    const left = sxToPx(t.stageX) - (t.fovW * scale) / 2;
    const top = syToPx(t.stageY) - (t.fovH * scale) / 2;
    ctx.strokeStyle = focusColor;
    ctx.lineWidth = isolated ? 2 : 1.5;
    ctx.strokeRect(left, top, t.fovW * scale, t.fovH * scale);
  }

  function drawHere(x: number, y: number, fw: number, fh: number) {
    if (!ctx) return;
    const px = sxToPx(x);
    const py = syToPx(y);
    const left = px - (fw * scale) / 2;
    const top = py - (fh * scale) / 2;
    ctx.strokeStyle = markerColor;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(left, top, fw * scale, fh * scale);
    ctx.beginPath();
    ctx.moveTo(px - 6, py);
    ctx.lineTo(px + 6, py);
    ctx.moveTo(px, py - 6);
    ctx.lineTo(px, py + 6);
    ctx.stroke();
  }

  // Measure the container from the DOM and keep the view size + backing store (device-pixel resolution)
  // in sync. A ResizeObserver can latch a 0 width during the mode-enter transition; clientWidth never does.
  function syncSize() {
    if (!containerEl || !canvasEl) return;
    const w = containerEl.clientWidth;
    const h = containerEl.clientHeight;
    if (w === viewW && h === viewH) return;
    viewW = w;
    viewH = h;
    if (w <= 0 || h <= 0) return;
    const dpr = devicePixelRatio;
    canvasEl.width = Math.round(w * dpr);
    canvasEl.height = Math.round(h * dpr);
    if (!userAdjusted) fitToContent();
    else clampPan(); // e.g. after the dock opens/closes and the canvas width changes
    needsRedraw = true;
  }

  function frameLoop() {
    if (!rendering) return;
    syncSize();
    if (needsRedraw && ctx && canvasEl) {
      needsRedraw = false;
      draw();
    }
    animId = requestAnimationFrame(frameLoop);
  }

  // Keep the snap page from ever showing nothing: when no folder is selected (a fresh refresh that
  // restored Snaps mode, or the viewed folder was deleted), fall back to the capture target. Keyed on
  // targetGroupId so it also fires once folders finish loading from IndexedDB.
  watch(
    () => [active, targetGroupId] as const,
    ([a]) => {
      if (!a) snaps.selectMostRecent();
    }
  );

  // Switching the viewed folder clears isolate and re-frames it —
  // even between same-size selections, where the content watch below wouldn't fire.
  watch(
    () => viewKey,
    () => {
      isolated = null;
      userAdjusted = false;
      fitToContent();
    }
  );

  // Geometry: a late-resolving container size or the stage frame appearing re-fits, while the user
  // hasn't taken over. (Content isn't a dependency here — new snaps must not move the camera.)
  watch(
    () => [viewW, viewH, stageBounds] as const,
    () => {
      if (!userAdjusted) fitToContent();
      needsRedraw = true;
    }
  );

  // Content: keep bitmaps in sync and drop a vanished isolate on any tile change, and redraw. Only
  // reframe when the user hasn't taken over AND a tile now sits out of view (e.g. a snap captured
  // off-screen) — an in-view capture leaves the camera untouched.
  watch(
    () => tiles.length,
    () => {
      if (!userAdjusted && tiles.length > 0 && !tilesInView()) fitToContent();
      pruneBitmaps(new Set(tiles.map((t) => t.id)));
      const i = isolated;
      if (i && !tiles.some((t) => t.id === i.id)) isolated = null; // focus auto-nulls via the store
      needsRedraw = true;
    }
  );

  // Viewport, MIP mode, focus/isolate, live stage position, and the stage frame all redraw.
  watch(
    () => [cx, cy, scale, mip, focused, isolated, hereX, hereY, stageBounds] as const,
    () => {
      needsRedraw = true;
    }
  );

  // ── Pan / zoom / click / double-click (stage-space, client-side) ──
  function hitTile(clientX: number, clientY: number): Snapshot | null {
    const rect = canvasEl.getBoundingClientRect();
    const sx = pxToSx(clientX - rect.left);
    const sy = pyToSy(clientY - rect.top);
    return tiles.find((t) => Math.abs(sx - t.stageX) <= t.fovW / 2 && Math.abs(sy - t.stageY) <= t.fovH / 2) ?? null;
  }

  function setupPanZoom(el: HTMLElement): () => void {
    let panning = false;
    let moved = false;
    let startX = 0;
    let startY = 0;
    let startCx = 0;
    let startCy = 0;
    const MOVE_THRESHOLD = 4;

    const down = (e: PointerEvent) => {
      if (e.button !== 0) return;
      el.setPointerCapture(e.pointerId);
      panning = true;
      moved = false;
      startX = e.clientX;
      startY = e.clientY;
      startCx = cx;
      startCy = cy;
    };

    const move = (e: PointerEvent) => {
      if (!panning) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      if (!moved && (Math.abs(dx) > MOVE_THRESHOLD || Math.abs(dy) > MOVE_THRESHOLD)) {
        moved = true;
        userAdjusted = true;
      }
      if (!moved) return;
      cx = startCx - orient.x * (dx / scale);
      cy = startCy + orient.y * (dy / scale);
      clampPan();
    };

    const up = (e: PointerEvent) => {
      if (e.button !== 0) return;
      el.releasePointerCapture(e.pointerId);
      panning = false;
      if (moved) return;
      const hit = hitTile(e.clientX, e.clientY); // single click = focus (no isolation)
      if (hit) snaps.focus(hit.id);
      else if (isGroup) snaps.focus(null); // clicking empty space unfocuses the tile
      isolated = null;
    };

    const dbl = (e: MouseEvent) => {
      const hit = hitTile(e.clientX, e.clientY); // double click = isolate (its pixels win)
      if (hit) {
        snaps.focus(hit.id);
        isolated = hit;
      }
    };

    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const stageUnderX = pxToSx(mx); // stage point under the cursor, kept fixed across the zoom
      const stageUnderY = pyToSy(my);
      scale = Math.max(minScale, Math.min(maxScale, scale / wheelZoomFactor(e)));
      cx = stageUnderX - orient.x * ((mx - viewW / 2) / scale);
      cy = stageUnderY + orient.y * ((my - viewH / 2) / scale);
      clampPan();
      userAdjusted = true;
    };

    el.addEventListener('pointerdown', down, { passive: true });
    el.addEventListener('pointermove', move, { passive: true });
    el.addEventListener('pointerup', up, { passive: true });
    el.addEventListener('dblclick', dbl);
    el.addEventListener('wheel', wheel, { passive: false });

    return () => {
      el.removeEventListener('pointerdown', down);
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('dblclick', dbl);
      el.removeEventListener('wheel', wheel);
    };
  }

  onMount(() => {
    ctx = canvasEl.getContext('2d');
    const styles = getComputedStyle(containerEl);
    markerColor = styles.getPropertyValue('--color-success').trim() || markerColor;
    focusColor = styles.getPropertyValue('--color-primary').trim() || focusColor;
    boundsColor = styles.getPropertyValue('--color-border').trim() || boundsColor;

    syncSize(); // measures + sizes the backing store + fits before the first frame
    rendering = true;
    needsRedraw = true;
    frameLoop();

    const teardown = setupPanZoom(canvasEl);
    return () => {
      rendering = false;
      if (animId !== null) cancelAnimationFrame(animId);
      teardown();
      for (const bmp of bitmaps.values()) bmp.close();
      bitmaps.clear();
    };
  });

  // ── Overlays ──
  const NICE_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000];

  const scaleBar = $derived.by(() => {
    const cw = viewW;
    if (cw <= 0 || scale <= 0) return null;
    const umPerPx = 1 / scale;
    const targetUm = umPerPx * cw * 0.2;
    const barUm = NICE_STEPS.findLast((s) => s <= targetUm) ?? NICE_STEPS[0];
    return { barPx: barUm * scale, label: barUm >= 1000 ? `${barUm / 1000} mm` : `${barUm} µm` };
  });

  const zLabel = $derived.by(() => {
    if (tiles.length === 0) return null;
    let lo = Infinity;
    let hi = -Infinity;
    for (const t of tiles) {
      lo = Math.min(lo, t.stageZ);
      hi = Math.max(hi, t.stageZ);
    }
    const span =
      Math.round(lo) === Math.round(hi) ? `Z ${Math.round(lo)} µm` : `Z ${Math.round(lo)}–${Math.round(hi)} µm`;
    return `${tiles.length} ${tiles.length === 1 ? 'tile' : 'tiles'} · ${span}`;
  });

  const shadow = 'drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]';
  const overlayCard = 'border border-border bg-surface/80 shadow-xl backdrop-blur-sm rounded-md';
</script>

{#snippet snapMenu(snap: Snapshot)}
  <ContextMenu.Item onSelect={() => goToSnap(snap)}>
    <Crosshair width="14" height="14" />
    Go to position
  </ContextMenu.Item>
  <ContextMenu.Item onSelect={() => recenterOn(snap)}>
    <CenterFocus width="14" height="14" />
    Recenter here
  </ContextMenu.Item>
  {#if groups.length > 1}
    <ContextMenu.Sub>
      <ContextMenu.SubTrigger>
        <FolderMoveOutline width="14" height="14" />
        Move to
      </ContextMenu.SubTrigger>
      <ContextMenu.SubContent class="min-w-40">
        {#each groups as g (g.id)}
          {#if g.id !== snap.groupId}
            <ContextMenu.Item onSelect={() => snaps.moveToSnapshotGroup(dragIds(snap.id), g.id)}>
              <FolderOpenOutline width="14" height="14" />
              {g.name}
            </ContextMenu.Item>
          {/if}
        {/each}
      </ContextMenu.SubContent>
    </ContextMenu.Sub>
  {/if}
  <ContextMenu.Separator />
  <ContextMenu.Item variant="destructive" onSelect={() => menuDelete(snap)}>
    <TrashCanOutline width="14" height="14" />
    {selected.has(snap.id) && selected.size > 1 ? `Delete ${selected.size}` : 'Delete'}
  </ContextMenu.Item>
{/snippet}

{#snippet posMenu(x: number, y: number)}
  <ContextMenu.Item onSelect={() => goToPos(x, y)}>
    <Crosshair width="14" height="14" />
    Go to position
  </ContextMenu.Item>
{/snippet}

{#snippet groupMenu(g: SnapshotGroup)}
  <ContextMenu.Item onSelect={() => snaps.setTarget(g.id)}>
    <Folder width="14" height="14" />
    Set as target
  </ContextMenu.Item>
  <ContextMenu.Item onSelect={() => startRename(g.id, g.name)}>
    <PencilOutline width="14" height="14" />
    Rename
  </ContextMenu.Item>
  <ContextMenu.Separator />
  <ContextMenu.Item variant="destructive" onSelect={() => snaps.deleteSnapshotGroup(g.id)}>
    <TrashCanOutline width="14" height="14" />
    Delete group
  </ContextMenu.Item>
{/snippet}

{#snippet snapRow(snap: Snapshot, indent: boolean)}
  {@const isActive = activeSnapId === snap.id}
  <ContextMenu.Root>
    <ContextMenu.Trigger>
      {#snippet child({ props })}
        <div
          {...props}
          use:draggable={{
            container: snap.groupId,
            dragData: { ids: dragIds(snap.id) },
            interactive: ['button'],
            attributes: { draggingClass: 'opacity-40' }
          }}
          class={cn(
            rowBase,
            'cursor-grab active:cursor-grabbing',
            indent && 'pl-6',
            selected.has(snap.id) ? 'bg-element-selected' : 'hover:bg-element-hover'
          )}
          role="button"
          tabindex="0"
          onpointerdown={(e) => e.button === 2 && pick(snap.id)}
          onclick={(e) => onRowClick(e, snap.id)}
          onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && onRowClick(e, snap.id)}
        >
          <img src={snap.thumbnail} alt="" class="h-6 w-8 shrink-0 rounded-sm border border-border object-cover" />
          <span class="min-w-0 flex-1 truncate {isActive ? 'text-fg' : 'text-fg-muted'}">{snap.label}</span>
          <span class="shrink-0 font-mono text-base text-fg-faint tabular-nums">z{Math.round(snap.stageZ)}</span>
        </div>
      {/snippet}
    </ContextMenu.Trigger>
    <ContextMenu.Content class="min-w-44">
      {@render snapMenu(snap)}
    </ContextMenu.Content>
  </ContextMenu.Root>
{/snippet}

<div class="flex h-full w-full overflow-hidden bg-canvas">
  <!-- Docked snapshot sidebar: toolbar + tree -->
  {#if sidebarOpen.current}
    <div
      class="flex w-64 shrink-0 flex-col overflow-hidden border-r border-border bg-surface/50"
      transition:slide={{ axis: 'x', duration: 200 }}
    >
      <div class="flex h-12 shrink-0 items-center gap-0.5 border-b border-border p-1.5">
        <Button variant="ghost" size="xs" title="New group" onclick={newGroup}>
          <Plus width="16" height="16" /> New Group
        </Button>
        <Button
          variant="ghost"
          size="icon-xs"
          class="ml-auto"
          title="Hide snapshots"
          onclick={() => (sidebarOpen.current = false)}
        >
          <PanelLeft width="16" height="16" />
        </Button>
      </div>

      <!-- Tree -->
      <div class="min-h-0 flex-1 overflow-y-auto p-1">
        {#each groups as g (g.id)}
          {@const groupTiles = snaps.tilesOf(g.id)}
          {@const open = !collapsed.has(g.id)}
          {@const isTarget = targetGroupId === g.id}
          <div
            use:droppable={{
              container: g.id,
              callbacks: { onDrop: (s) => handleDrop(s, g.id) },
              attributes: { dragOverClass: 'bg-info/10' }
            }}
            class="rounded-sm"
          >
            <ContextMenu.Root>
              <ContextMenu.Trigger>
                {#snippet child({ props })}
                  <div
                    {...props}
                    class={cn(
                      rowBase,
                      'cursor-pointer',
                      activeGroupId === g.id || selected.has(g.id) ? 'bg-element-selected' : 'hover:bg-element-hover'
                    )}
                    role="button"
                    tabindex="0"
                    onpointerdown={(e) => e.button === 2 && pick(g.id)}
                    onclick={(e) => onRowClick(e, g.id)}
                    onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && onRowClick(e, g.id)}
                  >
                    <button
                      type="button"
                      class="shrink-0 text-fg-muted hover:text-fg"
                      title={open ? 'Collapse' : 'Expand'}
                      onclick={(e) => {
                        e.stopPropagation();
                        toggleCollapse(g.id);
                      }}
                    >
                      {#if open}<ChevronDown width="14" height="14" />{:else}<ChevronRight
                          width="14"
                          height="14"
                        />{/if}
                    </button>
                    <button
                      type="button"
                      class="shrink-0"
                      title={isTarget ? 'Capture target' : 'Set as capture target'}
                      onclick={() => snaps.setTarget(g.id)}
                    >
                      {#if isTarget}
                        <Folder width="15" height="15" class="text-primary" />
                      {:else}
                        <FolderOpenOutline width="15" height="15" class="text-fg-muted hover:text-fg" />
                      {/if}
                    </button>
                    {#if renamingId === g.id}
                      <input
                        bind:value={renameValue}
                        class="border-focused min-w-0 flex-1 rounded-sm border bg-element-bg px-1 text-lg outline-none"
                        onclick={(e) => e.stopPropagation()}
                        onblur={commitRename}
                        onkeydown={renameKeydown}
                        {@attach (node) => {
                          (node as HTMLInputElement).focus();
                          (node as HTMLInputElement).select();
                        }}
                      />
                    {:else}
                      <span class="min-w-0 flex-1 truncate {isTarget ? 'text-fg' : ''}">{g.name}</span>
                    {/if}
                    <span class="shrink-0 rounded bg-element-bg px-1 text-base text-fg-muted tabular-nums">
                      {groupTiles.length}
                    </span>
                  </div>
                {/snippet}
              </ContextMenu.Trigger>
              <ContextMenu.Content class="min-w-44">
                {@render groupMenu(g)}
              </ContextMenu.Content>
            </ContextMenu.Root>
            {#if open}
              {#each groupTiles as tile (tile.id)}
                {@render snapRow(tile, true)}
              {/each}
            {/if}
          </div>
        {/each}
        {#if groups.length === 0}
          <p class="px-1.5 py-3 text-center text-base text-fg-faint">No snapshots yet</p>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Canvas area (its own overlays: expand, focused-snapshot card, live PiP, scale bar) -->
  <div bind:this={containerEl} class="relative min-w-0 flex-1 overflow-hidden bg-canvas">
    <ContextMenu.Root>
      <ContextMenu.Trigger class="block h-full w-full">
        <canvas
          bind:this={canvasEl}
          oncontextmenu={handleCanvasContext}
          class="h-full w-full cursor-grab touch-none active:cursor-grabbing"
        ></canvas>
      </ContextMenu.Trigger>
      <ContextMenu.Content class="min-w-44">
        {#if menuTarget?.kind === 'snap'}
          {@render snapMenu(menuTarget.snap)}
        {:else if menuTarget?.kind === 'pos'}
          {@render posMenu(menuTarget.x, menuTarget.y)}
        {/if}
      </ContextMenu.Content>
    </ContextMenu.Root>

    <!-- Top-left: expand (only when collapsed — the collapse control lives in the sidebar header) + MIP toggle -->
    <div class="absolute top-3 left-4 z-10 flex items-center gap-2">
      {#if !sidebarOpen.current}
        <Button variant="ghost" size="icon-xs" title="Show snapshots" onclick={() => (sidebarOpen.current = true)}>
          <PanelLeft width="16" height="16" />
        </Button>
      {/if}
      {#if group}
        <Button
          variant="ghost"
          size="icon-xs"
          title={group.mipEnabled ? 'Max projection on' : 'Max projection off'}
          class={cn(group.mipEnabled ? 'text-success' : 'text-fg-muted')}
          onclick={() => snaps.setSnapshotGroupMip(group.id, !group.mipEnabled)}
        >
          <Layers width="16" height="16" />
        </Button>
      {/if}
      {#if tiles.length > 0 || stageBounds}
        <Button variant="ghost" size="icon-xs" title="Fit all" onclick={fitAll}>
          <FitToScreen width="16" height="16" />
        </Button>
      {/if}
    </div>

    <!-- Live feed glimpse (top-right), only while a preview is running -->
    {#if livePreview}
      <button
        type="button"
        title="Back to live preview"
        onclick={() => app.view.goLive()}
        class="absolute top-4 right-4 z-10 block w-40 cursor-pointer overflow-hidden rounded-md border border-border/50 shadow-lg backdrop-blur-sm transition-colors hover:border-fg-muted"
        style:aspect-ratio={livePreview.boundingBoxAspect || 1}
      >
        <LiveThumbnail previewer={livePreview} class="h-full w-full" />
        <span
          class="pointer-events-none absolute top-1 left-1 flex items-center gap-1 rounded-sm bg-canvas/70 px-1 py-0.5 text-[10px] font-medium text-fg-muted"
        >
          <span class="h-1.5 w-1.5 rounded-full bg-danger"></span>
          Live
        </span>
      </button>
    {/if}

    <!-- Bottom-left: focused-tile detail card (when a tile is focused) above a persistent group line -->
    <div class="pointer-events-none absolute bottom-4 left-4 z-10 flex flex-col items-start gap-2">
      {#if focused && app.instrument}
        {@const f = focused}
        {@const inst = app.instrument}
        <div
          class={cn(
            'pointer-events-auto flex w-60 flex-col divide-y divide-border/50 overflow-hidden text-base',
            overlayCard
          )}
        >
          <!-- Name (double-click to rename) + profile -->
          <div class="flex min-h-8 items-center justify-between gap-2 px-2.5">
            <div class="min-w-0">
              <Rename
                value={f.label}
                size="sm"
                class="font-medium text-fg"
                textClass="truncate"
                onSave={(v) => snaps.rename(f.id, v)}
              />
            </div>
            {#if f.profileLabel}
              <span class="shrink-0 rounded bg-element-bg px-1.5 py-0.5 text-fg-muted">{f.profileLabel}</span>
            {/if}
          </div>

          {#each Object.entries(f.channels) as [name, ch] (name)}
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
      {/if}

      {#if group}
        <div class="flex max-w-72 items-center gap-1.5 text-base {shadow}">
          <span class="truncate font-medium text-fg">{group.name}</span>
          {#if zLabel}
            <span class="shrink-0 font-mono text-fg-muted tabular-nums">· {zLabel}</span>
          {/if}
        </div>
      {/if}
    </div>

    <!-- Scale bar, bottom-right -->
    {#if scaleBar}
      <div class="pointer-events-none absolute right-4 bottom-4 flex flex-col items-end gap-0.5">
        <span class="font-mono text-base text-fg-muted {shadow}">{scaleBar.label}</span>
        <div class="h-1 rounded-full bg-fg-muted {shadow}" style:width="{scaleBar.barPx}px"></div>
      </div>
    {/if}

    {#if tiles.length === 0 && !stageBounds}
      <div class="pointer-events-none absolute inset-0 grid place-content-center">
        <p class="text-lg text-fg-muted">{active ? 'Empty group' : 'No snapshots yet'}</p>
      </div>
    {/if}
  </div>
</div>
