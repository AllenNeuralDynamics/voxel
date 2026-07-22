<script lang="ts" module>
  export type MenuItem =
    | { type: 'action'; label: string; action: () => void; disabled?: boolean; variant?: 'destructive' }
    | { type: 'submenu'; label: string; items: MenuItem[]; disabled?: boolean }
    | { type: 'separator' };
</script>

<script lang="ts">
  import { watch } from 'runed';
  import { onMount } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';

  import { ContextMenu } from '$lib/kit';
  import { type AlignEdge, compositeFullFrames, type Instrument, type TaskTile } from '$lib/model';
  import { toastError } from '$lib/utils';

  import { getTaskSelection } from './selection.svelte';

  export interface LayerVisibility {
    grid: boolean;
    tasks: boolean;
    path: boolean;
    fov: boolean;
    thumbnail: boolean;
  }

  /** An auto-grid cell computed from the stencil (a potential tile position, not a placed task). */
  interface GridTile {
    row: number;
    col: number;
    x: number;
    y: number;
    w: number;
    h: number;
  }

  interface Props {
    instrument: Instrument;
    layers?: LayerVisibility;
  }

  let { instrument, layers = $bindable({ grid: true, tasks: true, path: true, fov: true, thumbnail: true }) }: Props =
    $props();

  // ── Geometry ─────────────────────────────────────────────────────────

  const sx = $derived(instrument.stage.x);
  const sy = $derived(instrument.stage.y);
  const sxLower = $derived(sx?.lowerLimit?.value ?? 0);
  const sxUpper = $derived(sx?.upperLimit?.value ?? 0);
  const syLower = $derived(sy?.lowerLimit?.value ?? 0);
  const syUpper = $derived(sy?.upperLimit?.value ?? 0);
  const sxPos = $derived(sx?.position?.value ?? 0);
  const syPos = $derived(sy?.position?.value ?? 0);
  const sxMoving = $derived(sx?.isMoving?.value === true);
  const syMoving = $derived(sy?.isMoving?.value === true);
  const stageWidth = $derived(sx?.range ?? 0);
  const stageHeight = $derived(sy?.range ?? 0);

  const fovW = $derived(instrument.fov?.[0] ?? 0);
  const fovH = $derived(instrument.fov?.[1] ?? 0);
  const activeProfileId = $derived(instrument.activeProfileId);

  const isXYMoving = $derived(sxMoving || syMoving);
  const isAcquiring = $derived(instrument.mode === 'capture');
  const arrowSize = $derived(Math.min(fovW, fovH) * 0.08);

  // ── Auto-grid computed from the stencil ──────────────────────────────

  const mosaicTiles = $derived.by<GridTile[]>(() => {
    if (!sx || !sy) return [];
    const s = instrument.state.stencil;
    const stepW = fovW * (1 - s.overlap_x);
    const stepH = fovH * (1 - s.overlap_y);
    if (stepW <= 0 || stepH <= 0) return [];
    const colMin = Math.ceil(-s.x_offset / stepW);
    const colMax = Math.floor((stageWidth - s.x_offset) / stepW) + 1;
    const rowMin = Math.ceil(-s.y_offset / stepH);
    const rowMax = Math.floor((stageHeight - s.y_offset) / stepH) + 1;
    const tiles: GridTile[] = [];
    for (let row = rowMin; row < rowMax; row++) {
      for (let col = colMin; col < colMax; col++) {
        const tx = s.x_offset + col * stepW;
        const ty = s.y_offset + row * stepH;
        if (tx >= 0 && tx <= stageWidth && ty >= 0 && ty <= stageHeight) {
          tiles.push({ row, col, x: tx, y: ty, w: fovW, h: fovH });
        }
      }
    }
    return tiles;
  });

  // ── Placed tasks (backend-computed footprints, in traversal order) ───

  const tasks = $derived(instrument.state.tasks);
  const taskTiles = $derived(instrument.taskTiles);
  const activeTiles = $derived(taskTiles.filter((t) => isActive(t.task_id)));

  function isActive(taskId: string): boolean {
    return activeProfileId ? (tasks[taskId]?.profile_ids.includes(activeProfileId) ?? false) : false;
  }

  /** Whether the active profile already has a task placed at (x, y). */
  function taskAt(x: number, y: number): boolean {
    return activeTiles.some((t) => Math.abs(t.x - x) < 1 && Math.abs(t.y - y) < 1);
  }

  // ── Selection (component-local) ──────────────────────────────────────

  const tileSelection = new SvelteSet<string>();
  const taskSelection = getTaskSelection();

  const tileKey = (row: number, col: number): string => `${row},${col}`;
  const isTileSelected = (row: number, col: number): boolean => tileSelection.has(tileKey(row, col));

  function selectTiles(cells: GridTile[]): void {
    tileSelection.clear();
    for (const { row, col } of cells) tileSelection.add(tileKey(row, col));
  }

  const selectedTiles = $derived(mosaicTiles.filter((t) => isTileSelected(t.row, t.col)));

  // ── FOV crosshair position (relative to stage origin) ────────────────

  const fovX = $derived(sx ? sxPos - sxLower : 0);
  const fovY = $derived(sy ? syPos - syLower : 0);

  // ── ViewBox + canvas sizing ──────────────────────────────────────────

  const tileHalfW = $derived(Math.max(fovW / 2, ...taskTiles.map((t) => t.w / 2)));
  const tileHalfH = $derived(Math.max(fovH / 2, ...taskTiles.map((t) => t.h / 2)));
  const marginX = $derived(Number.isFinite(tileHalfW) ? tileHalfW : fovW / 2);
  const marginY = $derived(Number.isFinite(tileHalfH) ? tileHalfH : fovH / 2);
  const viewBoxWidth = $derived(stageWidth + marginX * 2);
  const viewBoxHeight = $derived(stageHeight + marginY * 2);
  const viewBoxStr = $derived(`${-marginX} ${-marginY} ${viewBoxWidth} ${viewBoxHeight}`);

  let containerRef = $state<HTMLDivElement | null>(null);
  let canvasWidth = $state(400);
  let canvasHeight = $state(250);

  const aspectRatio = $derived(viewBoxWidth / viewBoxHeight);
  const scale = $derived(canvasWidth / viewBoxWidth);
  const stagePixelsX = $derived(stageWidth * scale);
  const stagePixelsY = $derived(stageHeight * scale);

  const XY_SLIDER_WIDTH = 16;

  const xSliderStyle = $derived(
    `left: ${marginX * scale}px; top: ${-XY_SLIDER_WIDTH / 2}px; width: ${stagePixelsX}px; height: ${XY_SLIDER_WIDTH}px;`
  );
  const ySliderStyle = $derived(
    `left: ${-XY_SLIDER_WIDTH / 2}px; top: ${marginY * scale}px; width: ${XY_SLIDER_WIDTH}px; height: ${stagePixelsY}px;`
  );
  const fovExtension = $derived(XY_SLIDER_WIDTH / 2 / scale);

  function fitCanvas(w: number, h: number) {
    if (w <= 0 || h <= 0) return;
    if (w / h > aspectRatio) {
      canvasHeight = h;
      canvasWidth = h * aspectRatio;
    } else {
      canvasWidth = w;
      canvasHeight = w / aspectRatio;
    }
  }

  onMount(() => {
    if (!containerRef) return;
    const observer = new ResizeObserver(([entry]) => fitCanvas(entry.contentRect.width, entry.contentRect.height));
    observer.observe(containerRef);
    return () => observer.disconnect();
  });

  $effect(() => {
    if (containerRef) {
      const { width, height } = containerRef.getBoundingClientRect();
      fitCanvas(width, height);
    }
  });

  // ── FOV thumbnail (live preview composite) ───────────────────────────

  const FOV_RESOLUTION = 256;
  let thumbnail = $state('');
  let needsRedraw = false;
  let animFrameId: number | null = null;

  const offscreen = document.createElement('canvas');
  offscreen.width = FOV_RESOLUTION;
  const ctx = offscreen.getContext('2d')!;

  $effect(() => {
    const aspect = fovW / fovH;
    if (aspect > 0 && Number.isFinite(aspect)) offscreen.height = Math.round(FOV_RESOLUTION / aspect);
  });

  watch(
    // Track frame index AND frame presence: on a profile switch the frames are cleared (frame → null)
    // while frame_idx is left as-is, so keying on the index alone would leave a stale thumbnail.
    () =>
      instrument.preview.channels.map((ch) => `${ch.latestFrameInfo?.frame_idx ?? -1}:${ch.frame ? 1 : 0}`).join(','),
    () => {
      needsRedraw = true;
    }
  );

  const shouldClearThumbnail = $derived(instrument.mode === 'idle' && isXYMoving);
  watch(
    () => shouldClearThumbnail,
    (clear) => {
      if (clear) thumbnail = '';
    }
  );

  function fovFrameLoop() {
    // Skip when the thumbnail layer is hidden — no point compositing/encoding what isn't shown.
    if (needsRedraw && layers.thumbnail) {
      needsRedraw = false;
      const channels = instrument.preview.channels;
      if (channels.some((ch) => ch.visible && ch.frame)) {
        compositeFullFrames(ctx, offscreen, channels);
        thumbnail = offscreen.toDataURL('image/png');
      } else {
        thumbnail = '';
      }
    }
    animFrameId = requestAnimationFrame(fovFrameLoop);
  }

  $effect(() => {
    fovFrameLoop();
    return () => {
      if (animFrameId !== null) cancelAnimationFrame(animFrameId);
    };
  });

  // ── Slider targets ───────────────────────────────────────────────────

  const stageTarget = $derived(instrument.stage.target);
  const targetPending = $derived(instrument.stage.targetPending);

  const displayX = $derived(targetPending && stageTarget?.x != null ? stageTarget.x : sxPos);
  const displayY = $derived(targetPending && stageTarget?.y != null ? stageTarget.y : syPos);

  function onSliderInputX(e: Event) {
    const v = parseFloat((e.target as HTMLInputElement).value);
    toastError(instrument.stage.moveTo({ x: v }));
  }

  function onSliderInputY(e: Event) {
    const v = parseFloat((e.target as HTMLInputElement).value);
    toastError(instrument.stage.moveTo({ y: v }));
  }

  // ── Interaction ──────────────────────────────────────────────────────

  function moveTo(x: number, y: number) {
    if (isXYMoving || !sx || !sy) return;
    toastError(instrument.stage.moveTo({ x: sxLower + x, y: syLower + y }));
  }

  function addTasksAt(positions: Array<{ x: number; y: number }>) {
    const xy = positions.filter((p) => !taskAt(p.x, p.y)).map((p): [number, number] => [p.x, p.y]);
    if (xy.length > 0) toastError(instrument.addTasks(xy, activeProfileId ? [activeProfileId] : undefined));
  }

  function handleTileSelect(e: MouseEvent, tile: GridTile) {
    taskSelection.clear();
    if (e.ctrlKey || e.metaKey) {
      if (isTileSelected(tile.row, tile.col)) tileSelection.delete(tileKey(tile.row, tile.col));
      else tileSelection.add(tileKey(tile.row, tile.col));
    } else {
      selectTiles([tile]);
    }
  }

  function handleTaskSelect(e: MouseEvent, taskId: string) {
    tileSelection.clear();
    if (e.ctrlKey || e.metaKey) taskSelection.toggle(taskId);
    else taskSelection.select(taskId);
  }

  function handleKeydown(e: KeyboardEvent, selectFn: () => void) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      selectFn();
    }
  }

  // ── Context menu ─────────────────────────────────────────────────────

  type ContextTarget =
    | { kind: 'tile'; tile: GridTile }
    | { kind: 'task'; tile: TaskTile }
    | { kind: 'empty'; x: number; y: number }
    | null;

  let contextTarget = $state<ContextTarget>(null);
  let clipboard = $state<{ x?: number; y?: number; start?: number; end?: number }>({});
  let svgRef = $state<SVGSVGElement | null>(null);

  /** Mouse event → SVG viewBox coordinates (stage-relative). */
  function svgPoint(e: MouseEvent): { x: number; y: number } | null {
    if (!svgRef) return null;
    const ctm = svgRef.getScreenCTM()?.inverse();
    if (!ctm) return null;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm);
    return { x: pt.x, y: pt.y };
  }

  function handleTileContext(tile: GridTile) {
    if (!isTileSelected(tile.row, tile.col)) selectTiles([tile]);
    taskSelection.clear();
    contextTarget = { kind: 'tile', tile };
  }

  function handleTaskContext(tile: TaskTile) {
    if (!taskSelection.has(tile.task_id)) taskSelection.select(tile.task_id);
    tileSelection.clear();
    contextTarget = { kind: 'task', tile };
  }

  function handleCanvasContext(e: MouseEvent) {
    if (e.target !== svgRef) return;
    const pt = svgPoint(e);
    if (!pt || !sx || !sy) return;
    contextTarget = { kind: 'empty', x: sxLower + pt.x, y: syLower + pt.y };
  }

  const menuItems = $derived.by<MenuItem[]>(() => {
    const target = contextTarget;
    if (!target) return [];
    if (isAcquiring) return [{ type: 'action', label: 'Acquisition in progress', action: () => {}, disabled: true }];

    const items: MenuItem[] = [];

    // Move here
    const moveAction = () => {
      if (target.kind === 'empty') moveTo(target.x - sxLower, target.y - syLower);
      else moveTo(target.tile.x, target.tile.y);
    };
    items.push({ type: 'action', label: 'Move here', action: moveAction, disabled: isXYMoving });

    // Select tiles (auto-grid only)
    if (target.kind === 'tile') {
      const tile = target.tile;
      items.push({
        type: 'submenu',
        label: 'Select tiles',
        items: [
          {
            type: 'action',
            label: `Row ${tile.row}`,
            action: () => selectTiles(mosaicTiles.filter((t) => t.row === tile.row))
          },
          {
            type: 'action',
            label: `Column ${tile.col}`,
            action: () => selectTiles(mosaicTiles.filter((t) => t.col === tile.col))
          },
          { type: 'separator' },
          { type: 'action', label: 'All', action: () => selectTiles(mosaicTiles) },
          {
            type: 'action',
            label: 'Invert',
            action: () => selectTiles(mosaicTiles.filter((t) => !isTileSelected(t.row, t.col)))
          }
        ]
      });
    }

    // Align grid (empty + task targets — tiles ARE the grid)
    if (target.kind !== 'tile') {
      const pos =
        target.kind === 'empty'
          ? { x: target.x, y: target.y }
          : { x: sxLower + target.tile.x, y: syLower + target.tile.y };
      items.push({
        type: 'submenu',
        label: 'Align grid',
        items: (['top', 'bottom', 'left', 'right', 'center'] as AlignEdge[]).map((edge) => ({
          type: 'action' as const,
          label: edge[0].toUpperCase() + edge.slice(1),
          action: () => toastError(instrument.alignStencil(edge, pos))
        }))
      });
    }

    // Copy / paste
    if (target.kind === 'tile' || target.kind === 'task') {
      const { x, y } = target.tile;
      items.push({ type: 'separator' });
      items.push({ type: 'action', label: 'Copy X', action: () => (clipboard = { ...clipboard, x }) });
      items.push({ type: 'action', label: 'Copy Y', action: () => (clipboard = { ...clipboard, y }) });
    }
    if (target.kind === 'task') {
      const t = tasks[target.tile.task_id];
      if (t) {
        items.push({
          type: 'action',
          label: 'Copy Z range',
          action: () => (clipboard = { ...clipboard, start: t.start, end: t.end })
        });
      }
      const selectedIds = taskSelection.list;
      if (clipboard.x !== undefined) {
        items.push({
          type: 'action',
          label: 'Paste X',
          action: () =>
            toastError(instrument.updateTasks(Object.fromEntries(selectedIds.map((id) => [id, { x: clipboard.x }]))))
        });
      }
      if (clipboard.y !== undefined) {
        items.push({
          type: 'action',
          label: 'Paste Y',
          action: () =>
            toastError(instrument.updateTasks(Object.fromEntries(selectedIds.map((id) => [id, { y: clipboard.y }]))))
        });
      }
      if (clipboard.start !== undefined && clipboard.end !== undefined) {
        items.push({
          type: 'action',
          label: 'Paste Z range',
          action: () =>
            toastError(
              instrument.updateTasks(
                Object.fromEntries(selectedIds.map((id) => [id, { start: clipboard.start, end: clipboard.end }]))
              )
            )
        });
      }
    }

    // Add task(s)
    if (target.kind === 'empty') {
      items.push({ type: 'separator' });
      items.push({
        type: 'action',
        label: 'Add task',
        action: () => addTasksAt([{ x: target.x - sxLower, y: target.y - syLower }])
      });
    } else if (target.kind === 'tile') {
      const empty = selectedTiles.filter((t) => !taskAt(t.x, t.y));
      if (empty.length > 0) {
        items.push({ type: 'separator' });
        items.push({
          type: 'action',
          label: empty.length === 1 ? 'Add task' : `Add tasks (${empty.length})`,
          action: () => addTasksAt(empty)
        });
      }
    }

    // Delete task(s)
    if (target.kind === 'task') {
      const ids = taskSelection.list;
      items.push({ type: 'separator' });
      items.push({
        type: 'action',
        label: ids.length <= 1 ? 'Delete task' : `Delete tasks (${ids.length})`,
        variant: 'destructive',
        action: () => toastError(instrument.removeTasks(ids))
      });
    }

    return items;
  });
</script>

{#snippet fovLayer()}
  {#if layers.thumbnail && thumbnail}
    <image
      href={thumbnail}
      x={fovX - fovW / 2}
      y={fovY - fovH / 2}
      width={fovW}
      height={fovH}
      preserveAspectRatio="xMidYMid slice"
      class="pointer-events-none"
    />
  {/if}
  <g class="pointer-events-none opacity-75">
    <line
      class="nss"
      x1={-marginX - fovExtension}
      y1={fovY}
      x2={-marginX + viewBoxWidth}
      y2={fovY}
      stroke-width="1"
      stroke={syMoving ? 'var(--color-danger)' : 'var(--color-success)'}
    />
    <line
      class="nss"
      x1={fovX}
      y1={-marginY - fovExtension}
      x2={fovX}
      y2={-marginY + viewBoxHeight}
      stroke-width="1"
      stroke={sxMoving ? 'var(--color-danger)' : 'var(--color-success)'}
    />
  </g>
{/snippet}

{#snippet gridLayer()}
  {#if layers.grid}
    {@const sorted = [...mosaicTiles].sort(
      (a, b) => Number(isTileSelected(a.row, a.col)) - Number(isTileSelected(b.row, b.col))
    )}
    <g>
      {#each sorted as tile (`${tile.row}_${tile.col}`)}
        {@const selected = isTileSelected(tile.row, tile.col)}
        <rect
          x={tile.x - tile.w / 2}
          y={tile.y - tile.h / 2}
          width={tile.w}
          height={tile.h}
          class="nss fill-transparent stroke-1 outline-none {selected ? 'stroke-fg/50' : 'stroke-border'}"
          class:cursor-pointer={!isXYMoving}
          class:cursor-not-allowed={isXYMoving}
          role="button"
          tabindex={isXYMoving ? -1 : 0}
          onclick={(e) => handleTileSelect(e, tile)}
          oncontextmenu={() => handleTileContext(tile)}
          onkeydown={(e) => handleKeydown(e, () => selectTiles([tile]))}
        >
          <title>Tile [{tile.row}, {tile.col}]</title>
        </rect>
      {/each}
    </g>
  {/if}
{/snippet}

{#snippet taskLayer()}
  {#if layers.tasks}
    {@const sorted = [...taskTiles].sort((a, b) => Number(isActive(a.task_id)) - Number(isActive(b.task_id)))}
    <g class="text-fg">
      {#each sorted as tile (tile.task_id)}
        {@const active = isActive(tile.task_id)}
        {@const selected = taskSelection.has(tile.task_id)}
        <rect
          x={tile.x - tile.w / 2}
          y={tile.y - tile.h / 2}
          width={tile.w}
          height={tile.h}
          class="nss outline-none"
          fill="currentColor"
          fill-opacity={active ? (selected ? 0.3 : 0.1) : 0.04}
          stroke="currentColor"
          stroke-opacity={selected ? 0.7 : active ? 0.35 : 0.18}
          stroke-width="1"
          class:cursor-pointer={!isXYMoving}
          class:cursor-not-allowed={isXYMoving}
          role="button"
          tabindex={isXYMoving ? -1 : 0}
          onclick={(e) => handleTaskSelect(e, tile.task_id)}
          oncontextmenu={() => handleTaskContext(tile)}
          onkeydown={(e) => handleKeydown(e, () => taskSelection.select(tile.task_id))}
        >
          <title>Task {tile.task_id}</title>
        </rect>
      {/each}
    </g>
  {/if}
{/snippet}

{#snippet pathLayer()}
  {#if layers.path && taskTiles.length > 1}
    {@const points = taskTiles.map((t) => ({ x: t.x, y: t.y }))}
    <g class="pointer-events-none text-fg-muted" stroke="currentColor" stroke-linecap="square">
      <polyline
        class="nss fill-none opacity-60"
        stroke-width="1.5"
        points={points.map((p) => `${p.x},${p.y}`).join(' ')}
      />
      {#each points.slice(0, -1) as p1, i (i)}
        {@const p2 = points[i + 1]}
        {@const dist = Math.hypot(p2.x - p1.x, p2.y - p1.y)}
        {#if dist > arrowSize}
          {@const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x) * (180 / Math.PI)}
          <path
            d="M {-arrowSize * 0.5} {-arrowSize * 0.6} L {arrowSize * 0.5} 0 L {-arrowSize * 0.5} {arrowSize * 0.6}"
            stroke-width={arrowSize * 0.15}
            class="fill-none opacity-90"
            transform="translate({(p1.x + p2.x) / 2}, {(p1.y + p2.y) / 2}) rotate({angle})"
          />
        {/if}
      {/each}
    </g>
  {/if}
{/snippet}

{#snippet renderMenuItems(items: MenuItem[])}
  {#each items as item, i (i)}
    {#if item.type === 'separator'}
      <ContextMenu.Separator />
    {:else if item.type === 'submenu'}
      <ContextMenu.Sub>
        <ContextMenu.SubTrigger disabled={item.disabled}>{item.label}</ContextMenu.SubTrigger>
        <ContextMenu.SubContent>
          {@render renderMenuItems(item.items ?? [])}
        </ContextMenu.SubContent>
      </ContextMenu.Sub>
    {:else}
      <ContextMenu.Item onSelect={item.action} disabled={item.disabled} variant={item.variant}>
        {item.label}
      </ContextMenu.Item>
    {/if}
  {/each}
{/snippet}

<div bind:this={containerRef} class="grid min-w-0 flex-1 place-content-center">
  <div class="relative" style="width: {canvasWidth}px; height: {canvasHeight}px;">
    <p class="absolute top-1 right-1 z-10 text-fg-muted">X / Y</p>
    <input
      type="range"
      class="stage-slider absolute z-10"
      style:--thumb-length="{XY_SLIDER_WIDTH}px"
      style={xSliderStyle}
      min={sxLower}
      max={sxUpper}
      step={100}
      value={displayX}
      disabled={sxMoving}
      oninput={onSliderInputX}
    />
    <input
      type="range"
      class="stage-slider vertical-ltr absolute z-10"
      style:--thumb-length="{XY_SLIDER_WIDTH}px"
      style={ySliderStyle}
      min={syLower}
      max={syUpper}
      step={100}
      value={displayY}
      disabled={syMoving}
      oninput={onSliderInputY}
    />
    <ContextMenu.Root>
      <ContextMenu.Trigger>
        <svg
          bind:this={svgRef}
          viewBox={viewBoxStr}
          class="border border-border-faint"
          style="width: {canvasWidth}px; height: {canvasHeight}px;"
          overflow="visible"
          role="img"
          oncontextmenu={handleCanvasContext}
        >
          {@render fovLayer()}
          {@render gridLayer()}
          {@render taskLayer()}
          {@render pathLayer()}
        </svg>
      </ContextMenu.Trigger>
      <ContextMenu.Content class="min-w-44">
        {@render renderMenuItems(menuItems)}
      </ContextMenu.Content>
    </ContextMenu.Root>
  </div>
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
    /* Transparent: the XYPlane's own border serves as the rail, so the slider blends into it. */
    --_track-color: transparent;
    --_track-width: 1px;
    --_track-bg: linear-gradient(var(--_track-color), var(--_track-color)) center / 100% var(--_track-width) no-repeat;

    &::-webkit-slider-runnable-track {
      background: var(--_track-bg);
      border-radius: 0;
    }
    &::-moz-range-track {
      background: var(--_track-bg);
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
    &.vertical-ltr {
      writing-mode: vertical-rl;
      direction: ltr;
      --_track-bg: linear-gradient(var(--_track-color), var(--_track-color)) center / var(--_track-width) 100% no-repeat;
    }
  }
</style>
