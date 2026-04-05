<script lang="ts" module>
  import type { Component } from 'svelte';
  import type { LayerVisibility } from '$lib/main/types';
  import { GridLines, StackLight, ImageLight } from '$lib/icons';

  // ── Layer visibility (module-level singleton) ────────────────────

  let layers = $state<LayerVisibility>({ grid: true, stacks: true, path: true, fov: true, thumbnail: true });

  const layerItems: { key: keyof LayerVisibility; color: string; Icon: Component; title: string }[] = [
    { key: 'grid', color: 'text-fg-muted', Icon: GridLines, title: 'Toggle grid' },
    { key: 'stacks', color: 'text-info', Icon: StackLight, title: 'Toggle stacks' },
    { key: 'thumbnail', color: 'text-success', Icon: ImageLight, title: 'Toggle thumbnail' }
  ];
</script>

<script lang="ts">
  import type { Session } from '$lib/main';
  import { type Tile, type Stack, type StackStatus } from '$lib/main/types';
  import { compositeFullFrames } from '$lib/main/preview.svelte';
  import { ContextMenu } from '$lib/ui/kit';
  import { SvelteSet } from 'svelte/reactivity';
  import { onMount } from 'svelte';
  import { watch } from 'runed';

  interface Props {
    session: Session;
  }

  let { session }: Props = $props();

  // ── Geometry ─────────────────────────────────────────────────────────

  let isXYMoving = $derived(session.stage.x?.isMoving || session.stage.y?.isMoving);
  let isAcquiring = $derived(session.mode === 'acquiring');
  let profileStacks = $derived(session.activeStacks);
  let arrowSize = $derived(Math.min(session.fov.width, session.fov.height) * 0.15);

  // ── Local tile selection ────────────────────────────────────────────

  let tileSelection = new SvelteSet<string>();

  function tileKey(row: number, col: number): string {
    return `${row},${col}`;
  }

  function isTileSelected(row: number, col: number): boolean {
    return tileSelection.has(tileKey(row, col));
  }

  function selectTiles(positions: Array<{ row: number; col: number }>): void {
    tileSelection.clear();
    for (const { row, col } of positions) {
      tileSelection.add(tileKey(row, col));
    }
  }

  function addTilesToSelection(positions: Array<{ row: number; col: number }>): void {
    for (const { row, col } of positions) {
      tileSelection.add(tileKey(row, col));
    }
  }

  function removeTilesFromSelection(positions: Array<{ row: number; col: number }>): void {
    for (const { row, col } of positions) {
      tileSelection.delete(tileKey(row, col));
    }
  }

  function clearTileSelection(): void {
    tileSelection.clear();
  }

  let selectedTilesList = $derived(session.tiles.filter((t) => isTileSelected(t.row, t.col)));

  // FOV position relative to stage origin (lower limits)
  let fovX = $derived(session.stage.x ? session.stage.x.position - session.stage.x.lowerLimit : 0);
  let fovY = $derived(session.stage.y ? session.stage.y.position - session.stage.y.lowerLimit : 0);
  // ViewBox: stage bounds + one FOV of margin on each side
  let marginX = $derived(session.fov.width / 2);
  let marginY = $derived(session.fov.height / 2);
  let viewBoxWidth = $derived(session.stage.width + session.fov.width);
  let viewBoxHeight = $derived(session.stage.height + session.fov.height);
  let viewBoxStr = $derived(`${-marginX} ${-marginY} ${viewBoxWidth} ${viewBoxHeight}`);

  // ── Canvas sizing ────────────────────────────────────────────────────

  let containerRef = $state<HTMLDivElement | null>(null);
  let canvasWidth = $state(400);
  let canvasHeight = $state(250);

  let aspectRatio = $derived(viewBoxWidth / viewBoxHeight);
  let scale = $derived(canvasWidth / viewBoxWidth);
  let stagePixelsX = $derived(session.stage.width * scale);
  let stagePixelsY = $derived(session.stage.height * scale);

  const XY_SLIDER_WIDTH = 16;

  let xSliderStyle = $derived(
    `left: ${marginX * scale}px; top: ${-XY_SLIDER_WIDTH / 2}px; width: ${stagePixelsX}px; height: ${XY_SLIDER_WIDTH}px;`
  );
  let ySliderStyle = $derived(
    `left: ${-XY_SLIDER_WIDTH / 2}px; top: ${marginY * scale}px; width: ${XY_SLIDER_WIDTH}px; height: ${stagePixelsY}px;`
  );

  let fovExtension = $derived(XY_SLIDER_WIDTH / 2 / scale);

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
    const observer = new ResizeObserver(([entry]) => {
      fitCanvas(entry.contentRect.width, entry.contentRect.height);
    });
    observer.observe(containerRef);
    return () => observer.disconnect();
  });

  $effect(() => {
    if (containerRef) {
      const { width, height } = containerRef.getBoundingClientRect();
      fitCanvas(width, height);
    }
  });

  // ── FOV thumbnail ────────────────────────────────────────────────────

  const FOV_RESOLUTION = 256;
  let thumbnail = $state('');
  let needsRedraw = false;
  let animFrameId: number | null = null;

  const offscreen = document.createElement('canvas');
  offscreen.width = FOV_RESOLUTION;
  const ctx = offscreen.getContext('2d')!;

  $effect(() => {
    const aspect = session.fov.width / session.fov.height;
    if (aspect > 0 && Number.isFinite(aspect)) {
      offscreen.height = Math.round(FOV_RESOLUTION / aspect);
    }
  });

  watch(
    () => session.preview?.redrawGeneration,
    () => {
      needsRedraw = true;
    }
  );

  function fovFrameLoop() {
    if (needsRedraw && session.preview) {
      needsRedraw = false;
      const hasFrames = session.preview.channels.some((ch) => ch.visible && ch.frame);
      if (hasFrames) {
        compositeFullFrames(ctx, offscreen, session.preview.channels);
        thumbnail = offscreen.toDataURL('image/jpeg', 0.6);
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

  // ── Slider targets ──────────────────────────────────────────────────

  let targetX = $state<number | null>(null);
  let targetY = $state<number | null>(null);

  let displayX = $derived(session.stage.x?.isMoving && targetX !== null ? targetX : (session.stage.x?.position ?? 0));
  let displayY = $derived(session.stage.y?.isMoving && targetY !== null ? targetY : (session.stage.y?.position ?? 0));

  function onSliderInputX(e: Event) {
    const v = parseFloat((e.target as HTMLInputElement).value);
    targetX = v;
    session.stage.x?.move(v);
  }

  function onSliderInputY(e: Event) {
    const v = parseFloat((e.target as HTMLInputElement).value);
    targetY = v;
    session.stage.y?.move(v);
  }

  // ── Interaction handlers ─────────────────────────────────────────────

  function moveToTilePosition(x: number, y: number) {
    if (isXYMoving || !session.stage.x || !session.stage.y) return;
    const tx = session.stage.x.lowerLimit + x;
    const ty = session.stage.y.lowerLimit + y;
    targetX = tx;
    targetY = ty;
    session.stage.moveXY(tx, ty);
  }

  function handleTileSelect(e: MouseEvent, tile: Tile) {
    session.clearStackSelection();
    if (e.ctrlKey || e.metaKey) {
      if (isTileSelected(tile.row, tile.col)) removeTilesFromSelection([tile]);
      else addTilesToSelection([tile]);
    } else {
      selectTiles([tile]);
    }
  }

  function handleStackSelect(e: MouseEvent, stack: Stack) {
    clearTileSelection();
    if (e.ctrlKey || e.metaKey) {
      if (session.isStackSelected(stack.stack_id)) {
        session.removeStacksFromSelection([stack]);
      } else {
        session.addStacksToSelection([stack]);
      }
    } else {
      session.selectStacks([stack]);
    }
  }

  function handleKeydown(e: KeyboardEvent, selectFn: () => void) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      selectFn();
    }
  }

  // ── Context menu ────────────────────────────────────────────────────

  type ContextTarget =
    | { kind: 'tile'; tile: Tile }
    | { kind: 'stack'; stack: Stack }
    | { kind: 'empty'; x: number; y: number }
    | null;

  type MenuContext =
    | { kind: 'empty'; x: number; y: number }
    | { kind: 'single-tile'; tile: Tile; stack: Stack | null }
    | { kind: 'multi-tile'; tile: Tile; withStacks: number; withoutStacks: number }
    | { kind: 'single-stack'; stack: Stack }
    | { kind: 'multi-stack'; stack: Stack; count: number };

  let contextTarget = $state<ContextTarget>(null);
  let zRangeBuffer = $state<{ zStartUm: number; zEndUm: number } | null>(null);
  let svgRef = $state<SVGSVGElement | null>(null);

  const STACK_STATUSES: StackStatus[] = ['planned', 'completed', 'failed', 'skipped'];

  let menuContext = $derived.by((): MenuContext | null => {
    if (!contextTarget) return null;
    if (contextTarget.kind === 'empty') return contextTarget;

    if (contextTarget.kind === 'stack') {
      const stack = contextTarget.stack;
      const selected = session.selectedStacks;
      if (selected.length <= 1) return { kind: 'single-stack', stack };
      return { kind: 'multi-stack', stack, count: selected.length };
    }

    // kind === 'tile'
    const tile = contextTarget.tile;
    const selected = selectedTilesList;
    if (selected.length <= 1) {
      return { kind: 'single-tile', tile, stack: session.getStackAtPosition(tile.x, tile.y) ?? null };
    }
    const withStacks = selected.filter((t) => session.getStackAtPosition(t.x, t.y)).length;
    return { kind: 'multi-tile', tile, withStacks, withoutStacks: selected.length - withStacks };
  });

  function handleTileContext(e: MouseEvent, tile: Tile) {
    if (!isTileSelected(tile.row, tile.col)) {
      selectTiles([tile]);
    }
    session.clearStackSelection();
    contextTarget = { kind: 'tile', tile };
  }

  function handleStackContext(e: MouseEvent, stack: Stack) {
    if (!session.isStackSelected(stack.stack_id)) {
      session.selectStacks([stack]);
    }
    clearTileSelection();
    contextTarget = { kind: 'stack', stack };
  }

  function handleCanvasContext(e: MouseEvent) {
    if (e.target !== svgRef) return;
    if (!svgRef || !session.stage.x || !session.stage.y) return;
    const ctm = svgRef.getScreenCTM()?.inverse();
    if (!ctm) return;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm);
    contextTarget = {
      kind: 'empty',
      x: session.stage.x.lowerLimit + pt.x,
      y: session.stage.y.lowerLimit + pt.y
    };
  }

  /** Stage-absolute position of the right-clicked item (for grid alignment). */
  function contextPosition(): { x: number; y: number } | undefined {
    if (!menuContext || !session.stage.x || !session.stage.y) return undefined;
    const lx = session.stage.x.lowerLimit;
    const ly = session.stage.y.lowerLimit;
    if (menuContext.kind === 'single-tile' || menuContext.kind === 'multi-tile') {
      return { x: lx + menuContext.tile.x, y: ly + menuContext.tile.y };
    }
    if (menuContext.kind === 'single-stack' || menuContext.kind === 'multi-stack') {
      return { x: lx + menuContext.stack.x, y: ly + menuContext.stack.y };
    }
    if (menuContext.kind === 'empty') {
      return { x: menuContext.x, y: menuContext.y };
    }
    return undefined;
  }

  function contextMoveHere() {
    if (isXYMoving || !menuContext) return;
    if (menuContext.kind === 'empty') {
      targetX = menuContext.x;
      targetY = menuContext.y;
      session.stage.moveXY(menuContext.x, menuContext.y);
    } else if (menuContext.kind === 'single-tile' || menuContext.kind === 'multi-tile') {
      moveToTilePosition(menuContext.tile.x, menuContext.tile.y);
    } else {
      moveToTilePosition(menuContext.stack.x, menuContext.stack.y);
    }
  }

  function contextAddStack() {
    const gc = session.gridConfig;
    if (!gc) return;
    const tiles = selectedTilesList.filter((t) => !session.getStackAtPosition(t.x, t.y));
    if (tiles.length === 0) return;
    session.addStacks(
      tiles.map((t) => ({
        x: t.x,
        y: t.y,
        zStartUm: gc.default_z_start,
        zEndUm: gc.default_z_end
      }))
    );
  }

  function contextDeleteStack() {
    if (menuContext?.kind === 'single-stack' || menuContext?.kind === 'multi-stack') {
      const stacks = session.selectedStacks;
      if (stacks.length > 0) session.removeStacks(stacks.map((s) => s.stack_id));
    } else {
      const stackIds = selectedTilesList
        .map((t) => session.getStackAtPosition(t.x, t.y))
        .filter((s): s is Stack => s !== undefined)
        .map((s) => s.stack_id);
      if (stackIds.length > 0) session.removeStacks(stackIds);
    }
  }

  function contextCopyZRange() {
    if (menuContext?.kind !== 'single-stack') return;
    zRangeBuffer = { zStartUm: menuContext.stack.z_start, zEndUm: menuContext.stack.z_end };
  }

  function contextPasteZRange() {
    if (!zRangeBuffer) return;
    let edits: Array<{ stackId: string; zStartUm: number; zEndUm: number }>;
    if (menuContext?.kind === 'single-stack' || menuContext?.kind === 'multi-stack') {
      edits = session.selectedStacks.map((s) => ({
        stackId: s.stack_id,
        zStartUm: zRangeBuffer!.zStartUm,
        zEndUm: zRangeBuffer!.zEndUm
      }));
    } else {
      edits = selectedTilesList
        .map((t) => session.getStackAtPosition(t.x, t.y))
        .filter((s): s is Stack => s !== undefined)
        .map((s) => ({
          stackId: s.stack_id,
          zStartUm: zRangeBuffer!.zStartUm,
          zEndUm: zRangeBuffer!.zEndUm
        }));
    }
    if (edits.length > 0) session.editStacks(edits);
  }
</script>

{#snippet fovLayer()}
  {#if layers.thumbnail && thumbnail}
    <image
      href={thumbnail}
      x={fovX - session.fov.width / 2}
      y={fovY - session.fov.height / 2}
      width={session.fov.width}
      height={session.fov.height}
      preserveAspectRatio="xMidYMid slice"
      class="pointer-events-none"
    />
  {/if}
  <g class="pointer-events-none">
    <line
      class="nss"
      x1={-marginX - fovExtension}
      y1={fovY}
      x2={-marginX + viewBoxWidth}
      y2={fovY}
      stroke-width="1"
      stroke={session.stage.y?.isMoving ? 'var(--color-danger)' : 'var(--color-success)'}
    />
    <line
      class="nss"
      x1={fovX}
      y1={-marginY - fovExtension}
      x2={fovX}
      y2={-marginY + viewBoxHeight}
      stroke-width="1"
      stroke={session.stage.x?.isMoving ? 'var(--color-danger)' : 'var(--color-success)'}
    />
  </g>
{/snippet}

{#snippet gridLayer()}
  {#if layers.grid}
    {@const sortedTiles = [...session.tiles].sort(
      (a, b) => Number(isTileSelected(a.row, a.col)) - Number(isTileSelected(b.row, b.col))
    )}
    <g>
      {#each sortedTiles as tile (`${tile.row}_${tile.col}`)}
        {@const selected = isTileSelected(tile.row, tile.col)}
        {@const cx = tile.x}
        {@const cy = tile.y}
        {@const w = tile.w}
        {@const h = tile.h}
        <rect
          x={cx - w / 2}
          y={cy - h / 2}
          width={w}
          height={h}
          class="nss fill-transparent stroke-1 outline-none {selected ? 'stroke-fg/50' : 'stroke-border'}"
          class:cursor-pointer={!isXYMoving}
          class:cursor-not-allowed={isXYMoving}
          role="button"
          tabindex={isXYMoving ? -1 : 0}
          onclick={(e) => handleTileSelect(e, tile)}
          oncontextmenu={(e) => handleTileContext(e, tile)}
          onkeydown={(e) => handleKeydown(e, () => selectTiles([tile]))}
        >
          <title>Tile [{tile.row}, {tile.col}]</title>
        </rect>
      {/each}
    </g>
  {/if}
{/snippet}

{#snippet stacksLayer()}
  {#if layers.stacks}
    {@const points = profileStacks.map((s) => ({ x: s.x, y: s.y }))}
    <g>
      {#each profileStacks as stack (stack.stack_id)}
        {@const selected = session.isStackSelected(stack.stack_id)}
        {@const cx = stack.x}
        {@const cy = stack.y}
        {@const w = stack.w}
        {@const h = stack.h}
        <rect
          x={cx - w / 2}
          y={cy - h / 2}
          width={w}
          height={h}
          data-stack-status={stack.status}
          class="nss text-(--stack-status) outline-none"
          fill="currentColor"
          fill-opacity={selected ? '0.35' : '0.15'}
          stroke={selected ? 'currentColor' : 'none'}
          stroke-width={selected ? '1' : '0'}
          class:cursor-pointer={!isXYMoving}
          class:cursor-not-allowed={isXYMoving}
          role="button"
          tabindex={isXYMoving ? -1 : 0}
          onclick={(e) => handleStackSelect(e, stack)}
          oncontextmenu={(e) => handleStackContext(e, stack)}
          onkeydown={(e) => handleKeydown(e, () => session.selectStacks([stack]))}
        >
          <title>Stack {stack.stack_id} - {stack.status} ({stack.num_frames} frames)</title>
        </rect>
      {/each}
    </g>
    <g class="pointer-events-none text-fg-muted" stroke="currentColor" stroke-linecap="square">
      <polyline
        class="nss fill-none opacity-35"
        stroke-width="1.5"
        points={points.map((p) => `${p.x},${p.y}`).join(' ')}
      />
      {#each points.slice(0, -1) as p1, i (i)}
        {@const p2 = points[i + 1]}
        {@const midX = (p1.x + p2.x) / 2}
        {@const midY = (p1.y + p2.y) / 2}
        {@const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x) * (180 / Math.PI)}
        <path
          d="M {-arrowSize * 0.5} {-arrowSize * 0.6} L {arrowSize * 0.5} 0 L {-arrowSize * 0.5} {arrowSize * 0.6}"
          stroke-width={arrowSize * 0.15}
          class="fill-none opacity-70"
          transform="translate({midX}, {midY}) rotate({angle})"
        />
      {/each}
    </g>
  {/if}
{/snippet}

{#snippet alignGridItems()}
  {@const pos = contextPosition()}
  <ContextMenu.Sub>
    <ContextMenu.SubTrigger disabled={!session.gridConfig}>Align grid</ContextMenu.SubTrigger>
    <ContextMenu.SubContent>
      <ContextMenu.Item onSelect={() => session.alignGrid('top', pos)}>Top</ContextMenu.Item>
      <ContextMenu.Item onSelect={() => session.alignGrid('bottom', pos)}>Bottom</ContextMenu.Item>
      <ContextMenu.Item onSelect={() => session.alignGrid('left', pos)}>Left</ContextMenu.Item>
      <ContextMenu.Item onSelect={() => session.alignGrid('right', pos)}>Right</ContextMenu.Item>
      <ContextMenu.Separator />
      <ContextMenu.Item onSelect={() => session.alignGrid('center', pos)}>Center</ContextMenu.Item>
    </ContextMenu.SubContent>
  </ContextMenu.Sub>
{/snippet}

{#snippet tileContextItems()}
  <ContextMenu.Sub>
    <ContextMenu.SubTrigger>Select tiles</ContextMenu.SubTrigger>
    <ContextMenu.SubContent>
      {#if menuContext?.kind === 'single-tile' || menuContext?.kind === 'multi-tile'}
        <ContextMenu.Item onSelect={() => selectTiles(session.tiles.filter((t) => t.row === menuContext.tile.row))}>
          Row {menuContext.tile.row}
        </ContextMenu.Item>
        <ContextMenu.Item onSelect={() => selectTiles(session.tiles.filter((t) => t.col === menuContext.tile.col))}>
          Column {menuContext.tile.col}
        </ContextMenu.Item>
        <ContextMenu.Separator />
      {/if}
      <ContextMenu.Item onSelect={() => selectTiles(session.tiles)}>All</ContextMenu.Item>
      {#if selectedTilesList.length > 0}
        <ContextMenu.Item onSelect={() => clearTileSelection()}>Deselect all</ContextMenu.Item>
      {/if}
      <ContextMenu.Item onSelect={() => selectTiles(session.tiles.filter((t) => !isTileSelected(t.row, t.col)))}>
        Invert
      </ContextMenu.Item>
      {#if profileStacks.length > 0 || session.tiles.length > 0}
        <ContextMenu.Separator />
      {/if}
      {#if profileStacks.length > 0}
        <ContextMenu.Item
          onSelect={() => selectTiles(session.tiles.filter((t) => session.getStackAtPosition(t.x, t.y)))}
        >
          With stacks
        </ContextMenu.Item>
      {/if}
      {#if session.tiles.length > 0}
        <ContextMenu.Item
          onSelect={() => selectTiles(session.tiles.filter((t) => !session.getStackAtPosition(t.x, t.y)))}
        >
          Without stacks
        </ContextMenu.Item>
      {/if}
    </ContextMenu.SubContent>
  </ContextMenu.Sub>

  {@render alignGridItems()}

  {#if menuContext?.kind === 'single-tile'}
    {#if !menuContext.stack}
      <ContextMenu.Separator />
      <ContextMenu.Item onSelect={contextAddStack}>Add stack</ContextMenu.Item>
    {/if}
  {:else if menuContext?.kind === 'multi-tile'}
    {#if menuContext.withoutStacks > 0}
      <ContextMenu.Separator />
      <ContextMenu.Item onSelect={contextAddStack}>
        Add stacks ({menuContext.withoutStacks})
      </ContextMenu.Item>
    {/if}
  {/if}
{/snippet}

{#snippet stackContextItems()}
  <ContextMenu.Sub>
    <ContextMenu.SubTrigger>Select stacks</ContextMenu.SubTrigger>
    <ContextMenu.SubContent>
      <ContextMenu.Item onSelect={() => session.selectMultipleStacks({ profileIds: [session.activeProfileId!] })}>All</ContextMenu.Item>
      {#if session.selectedStacks.length > 0}
        <ContextMenu.Item onSelect={() => session.clearStackSelection()}>Deselect all</ContextMenu.Item>
      {/if}
      {#if profileStacks.length > 0}
        <ContextMenu.Separator />
        {#each STACK_STATUSES as status (status)}
          <ContextMenu.Item onSelect={() => session.selectMultipleStacks({ profileIds: [session.activeProfileId!], status: [status] })}>
            {status[0].toUpperCase() + status.slice(1)}
          </ContextMenu.Item>
        {/each}
      {/if}
    </ContextMenu.SubContent>
  </ContextMenu.Sub>

  {@render alignGridItems()}

  <ContextMenu.Separator />
  {#if menuContext?.kind === 'single-stack'}
    <ContextMenu.Sub>
      <ContextMenu.SubTrigger>Z range</ContextMenu.SubTrigger>
      <ContextMenu.SubContent>
        <ContextMenu.Item onSelect={contextCopyZRange}>Copy</ContextMenu.Item>
        {#if zRangeBuffer}
          <ContextMenu.Item onSelect={contextPasteZRange}>Paste</ContextMenu.Item>
        {/if}
      </ContextMenu.SubContent>
    </ContextMenu.Sub>
    <ContextMenu.Item variant="destructive" onSelect={contextDeleteStack}>Delete stack</ContextMenu.Item>
  {:else if menuContext?.kind === 'multi-stack'}
    {#if zRangeBuffer}
      <ContextMenu.Item onSelect={contextPasteZRange}>
        Paste Z range ({menuContext.count})
      </ContextMenu.Item>
    {/if}
    <ContextMenu.Item variant="destructive" onSelect={contextDeleteStack}>
      Delete stacks ({menuContext.count})
    </ContextMenu.Item>
  {/if}
{/snippet}

{#snippet contextMenuItems()}
  {#if isAcquiring}
    <ContextMenu.Item disabled>Acquisition in progress</ContextMenu.Item>
  {:else}
    <ContextMenu.Item disabled={isXYMoving} onSelect={contextMoveHere}>Move here</ContextMenu.Item>

    {#if menuContext?.kind === 'single-tile' || menuContext?.kind === 'multi-tile'}
      {@render tileContextItems()}
    {:else if menuContext?.kind === 'single-stack' || menuContext?.kind === 'multi-stack'}
      {@render stackContextItems()}
    {/if}
  {/if}
{/snippet}

<div bind:this={containerRef} class="grid min-w-0 flex-1 place-content-center">
  <div class="relative" style="width: {canvasWidth}px; height: {canvasHeight}px;">
    <p class="absolute top-1 right-1 z-10 text-xs text-fg-muted">X / Y</p>
    <input
      type="range"
      class="stage-slider absolute z-10"
      style:--thumb-length="{XY_SLIDER_WIDTH}px"
      style={xSliderStyle}
      min={session.stage.x.lowerLimit}
      max={session.stage.x.upperLimit}
      step={100}
      value={displayX}
      disabled={session.stage.x.isMoving}
      oninput={onSliderInputX}
    />
    <input
      type="range"
      class="stage-slider vertical-ltr absolute z-10"
      style:--thumb-length="{XY_SLIDER_WIDTH}px"
      style={ySliderStyle}
      min={session.stage.y.lowerLimit}
      max={session.stage.y.upperLimit}
      step={100}
      value={displayY}
      disabled={session.stage.y.isMoving}
      oninput={onSliderInputY}
    />
    <div class="absolute right-1 bottom-1 z-10 flex items-center gap-1 rounded-full">
      {#each layerItems as { key, color, Icon, title } (key)}
        <button
          onclick={() => (layers[key] = !layers[key])}
          class="cursor-pointer rounded-full p-1.5 transition-colors {layers[key] ? `${color} ` : 'text-fg-faint'}"
          {title}
        >
          <Icon width="14" height="14" />
        </button>
      {/each}
    </div>
    <ContextMenu.Root>
      <ContextMenu.Trigger>
        <svg
          bind:this={svgRef}
          viewBox={viewBoxStr}
          class="border border-fg-faint/70"
          style="width: {canvasWidth}px; height: {canvasHeight}px;"
          overflow="visible"
          role="img"
          oncontextmenu={handleCanvasContext}
        >
          {@render fovLayer()}
          {@render gridLayer()}
          {@render stacksLayer()}
        </svg>
      </ContextMenu.Trigger>
      <ContextMenu.Content class="min-w-44">
        {@render contextMenuItems()}
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
    --_track-color: var(--color-border);
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
