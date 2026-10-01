<script lang="ts">
  import { type Component, onMount } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';

  import { page } from '$app/state';
  import { Crosshair, GridLines, PathLight, StackLight } from '$lib/icons';
  import { ContextMenu } from '$lib/kit';
  import { createPositionTask, getVoxelStation, type PlannedVolume, planningFov, type Point2D } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';
  import { prefs } from '$lib/prefs';
  import { formatSpatialDistance } from '$lib/spatial-units';
  import { toastError } from '$lib/utils';

  interface LayerVisibility {
    grid: boolean;
    volumes: boolean;
    path: boolean;
    fov: boolean;
  }

  interface GridTile {
    row: number;
    col: number;
    x: number;
    y: number;
    width: number;
    height: number;
  }

  interface Bounds {
    minX: number;
    minY: number;
    maxX: number;
    maxY: number;
  }

  interface VolumeFootprint {
    bounds: Bounds;
    key: string;
    order: number;
    profile: string;
    task: string;
    volume: PlannedVolume;
  }

  type ContextTarget =
    | { kind: 'tile'; tile: GridTile }
    | { kind: 'volume'; footprint: VolumeFootprint }
    | { kind: 'empty'; x: number; y: number }
    | null;

  type MenuItem =
    | { type: 'action'; label: string; action: () => void; disabled?: boolean; variant?: 'destructive' }
    | { type: 'submenu'; label: string; items: MenuItem[] }
    | { type: 'separator' };

  const app = getVoxelStation();
  const instrument = $derived(app.instrument?.id === page.params.instrumentId ? app.instrument : null);
  const preferenceKey = $derived(`${page.params.stationId ?? ''}/${page.params.instrumentId ?? ''}`);
  const taskRange = $derived.by(() => {
    const saved = prefs.plan.defaults.get()[preferenceKey];
    if (saved) return saved.zRange;
    const z = instrument?.stage.z.position?.value;
    return z != null && Number.isFinite(z) ? { start: z, end: z } : null;
  });

  let layers = $state<LayerVisibility>({ grid: true, volumes: true, path: true, fov: true });
  const layerItems: { key: keyof LayerVisibility; color: string; Icon: Component; title: string }[] = [
    { key: 'grid', color: 'text-fg-muted', Icon: GridLines, title: 'Toggle grid' },
    { key: 'volumes', color: 'text-info', Icon: StackLight, title: 'Toggle planned volumes' },
    { key: 'path', color: 'text-warning', Icon: PathLight, title: 'Toggle acquisition path' },
    { key: 'fov', color: 'text-success', Icon: Crosshair, title: 'Toggle field of view' }
  ];

  const sx = $derived(instrument?.stage.x ?? null);
  const sy = $derived(instrument?.stage.y ?? null);
  const sz = $derived(instrument?.stage.z ?? null);
  const sxLower = $derived(sx?.lowerLimit?.value ?? 0);
  const sxUpper = $derived(sx?.upperLimit?.value ?? 0);
  const syLower = $derived(sy?.lowerLimit?.value ?? 0);
  const syUpper = $derived(sy?.upperLimit?.value ?? 0);
  const zLower = $derived(sz?.lowerLimit?.value ?? 0);
  const zUpper = $derived(sz?.upperLimit?.value ?? 0);
  const sxPos = $derived(sx?.position?.value ?? 0);
  const syPos = $derived(sy?.position?.value ?? 0);
  const zPos = $derived(sz?.position?.value ?? 0);
  const sxMoving = $derived(sx?.isMoving?.value === true);
  const syMoving = $derived(sy?.isMoving?.value === true);
  const zMoving = $derived(sz?.isMoving?.value === true);
  const isXYMoving = $derived(sxMoving || syMoving);
  const stageWidth = $derived(sx?.range ?? 0);
  const stageHeight = $derived(sy?.range ?? 0);
  const stageDepth = $derived(sz?.range ?? 0);
  const activeProfile = $derived(
    instrument?.activeProfileId || Object.keys(instrument?.imaging.profiles ?? {})[0] || null
  );
  const gridFov = $derived(activeProfile && instrument ? planningFov(instrument.profileFovs, [activeProfile]) : null);
  const fovWidth = $derived(gridFov?.[0] ?? instrument?.fov?.[0] ?? 0);
  const fovHeight = $derived(gridFov?.[1] ?? instrument?.fov?.[1] ?? 0);
  const orientation = $derived(instrument?.stage.orientation ?? { x: 1, y: 1, z: 1 });
  const ox = $derived(orientation.x);
  const oy = $derived(-orientation.y);
  const disabled = $derived(!instrument || instrument.mode === 'capture' || instrument.edits.busy);

  const taskNumbers = $derived(new Map(instrument?.plan.map((task, index) => [task.id, index + 1]) ?? []));

  const footprints = $derived.by<VolumeFootprint[]>(() => {
    const result: VolumeFootprint[] = [];
    for (const [index, volume] of (instrument?.plannedVolumes ?? []).entries()) {
      const seen: string[] = [];
      for (const footprint of Object.values(instrument?.profileFovs[volume.profile] ?? {})) {
        const bounds = {
          minX: volume.x + footprint.min.x,
          minY: volume.y + footprint.min.y,
          maxX: volume.x + footprint.max.x,
          maxY: volume.y + footprint.max.y
        };
        const boundsKey = `${bounds.minX}:${bounds.minY}:${bounds.maxX}:${bounds.maxY}`;
        if (seen.includes(boundsKey)) continue;
        seen.push(boundsKey);
        result.push({
          bounds,
          key: `${index + 1}:${boundsKey}`,
          order: index + 1,
          profile: volume.profile,
          task: volume.task,
          volume
        });
      }
    }
    return result;
  });

  const GRID_OVERLAP = 0.1;
  const gridTiles = $derived.by<GridTile[]>(() => {
    const stepX = fovWidth * (1 - GRID_OVERLAP);
    const stepY = fovHeight * (1 - GRID_OVERLAP);
    if (stageWidth <= 0 || stageHeight <= 0 || stepX <= 0 || stepY <= 0) return [];
    const result: GridTile[] = [];
    const columns = Math.floor(stageWidth / stepX) + 1;
    const rows = Math.floor(stageHeight / stepY) + 1;
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < columns; col++) {
        const x = col * stepX;
        const y = row * stepY;
        if (x <= stageWidth && y <= stageHeight) result.push({ row, col, x, y, width: fovWidth, height: fovHeight });
      }
    }
    return result;
  });

  const pathPoints = $derived.by(() => {
    const result: Array<Point2D & { task: string }> = [];
    for (const { task, x, y } of instrument?.plannedVolumes ?? []) {
      const previous = result.at(-1);
      if (!previous || previous.task !== task || previous.x !== x || previous.y !== y) result.push({ task, x, y });
    }
    return result;
  });

  const tileSelection = new SvelteSet<string>();
  let selectedTask = $state<string | null>(null);
  const tileKey = (tile: GridTile) => `${tile.row},${tile.col}`;
  const tileSelected = (tile: GridTile) => tileSelection.has(tileKey(tile));
  const selectedTiles = $derived(gridTiles.filter(tileSelected));

  function selectTiles(tiles: readonly GridTile[]): void {
    tileSelection.clear();
    for (const tile of tiles) tileSelection.add(tileKey(tile));
  }

  function handleTileSelect(event: MouseEvent, tile: GridTile): void {
    selectedTask = null;
    if (event.metaKey || event.ctrlKey) {
      if (!tileSelection.delete(tileKey(tile))) tileSelection.add(tileKey(tile));
    } else {
      selectTiles([tile]);
    }
  }

  function handleVolumeSelect(footprint: VolumeFootprint): void {
    tileSelection.clear();
    selectedTask = selectedTask === footprint.task ? null : footprint.task;
  }

  function handleKeydown(event: KeyboardEvent, action: () => void): void {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    action();
  }

  const gridToStage = (tile: GridTile): Point2D => ({ x: sxLower + tile.x, y: syLower + tile.y });
  const hasVolumeAt = ({ x, y }: Point2D) =>
    (instrument?.plannedVolumes ?? []).some(
      (volume) => volume.profile === activeProfile && Math.abs(volume.x - x) < 1 && Math.abs(volume.y - y) < 1
    );

  function addPositions(points: readonly Point2D[]): void {
    const inst = instrument;
    const profile = activeProfile;
    const unique = points.filter((point) => !hasVolumeAt(point));
    if (!inst || !profile || !taskRange || !unique.length || disabled) return;
    toastError(inst.addTask(createPositionTask(unique, profile, taskRange)));
  }

  function moveTo({ x, y }: Point2D): void {
    const inst = instrument;
    if (!inst || isXYMoving) return;
    toastError(inst.stage.moveTo({ x, y }));
  }

  let contextTarget = $state<ContextTarget>(null);
  let svgRef = $state<SVGSVGElement | null>(null);

  function svgPoint(event: MouseEvent): Point2D | null {
    const transform = svgRef?.getScreenCTM()?.inverse();
    if (!transform) return null;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(transform);
    return { x: sxLower + point.x * ox, y: syLower + point.y * oy };
  }

  function handleCanvasContext(event: MouseEvent): void {
    if (event.target !== svgRef) return;
    const point = svgPoint(event);
    if (point) contextTarget = { kind: 'empty', ...point };
  }

  function handleTileContext(tile: GridTile): void {
    if (!tileSelected(tile)) selectTiles([tile]);
    selectedTask = null;
    contextTarget = { kind: 'tile', tile };
  }

  function handleVolumeContext(footprint: VolumeFootprint): void {
    selectedTask = footprint.task;
    tileSelection.clear();
    contextTarget = { kind: 'volume', footprint };
  }

  const menuItems = $derived.by<MenuItem[]>(() => {
    const inst = instrument;
    const target = contextTarget;
    if (!inst || !target) return [];
    if (inst.mode === 'capture')
      return [{ type: 'action', label: 'Acquisition in progress', action: () => {}, disabled: true }];

    const point =
      target.kind === 'tile'
        ? gridToStage(target.tile)
        : target.kind === 'volume'
          ? { x: target.footprint.volume.x, y: target.footprint.volume.y }
          : target;
    const items: MenuItem[] = [
      { type: 'action', label: 'Move here', action: () => moveTo(point), disabled: isXYMoving }
    ];

    if (target.kind === 'tile') {
      items.push({
        type: 'submenu',
        label: 'Select tiles',
        items: [
          {
            type: 'action',
            label: `Row ${target.tile.row}`,
            action: () => selectTiles(gridTiles.filter((tile) => tile.row === target.tile.row))
          },
          {
            type: 'action',
            label: `Column ${target.tile.col}`,
            action: () => selectTiles(gridTiles.filter((tile) => tile.col === target.tile.col))
          },
          { type: 'separator' },
          { type: 'action', label: 'All', action: () => selectTiles(gridTiles) },
          {
            type: 'action',
            label: 'Invert',
            action: () => selectTiles(gridTiles.filter((tile) => !tileSelected(tile)))
          }
        ]
      });
    }

    if (target.kind === 'empty' || target.kind === 'tile') {
      const points =
        target.kind === 'empty'
          ? [point]
          : selectedTiles.map(gridToStage).filter((candidate) => !hasVolumeAt(candidate));
      items.push({ type: 'separator' });
      items.push({
        type: 'action',
        label: points.length === 1 ? 'Add position task' : `Add position task (${points.length} positions)`,
        action: () => addPositions(points),
        disabled: disabled || !points.length || !taskRange || !activeProfile
      });
    }

    if (target.kind === 'volume') {
      const taskNumber = taskNumbers.get(target.footprint.task);
      items.push({ type: 'separator' });
      items.push({
        type: 'action',
        label: taskNumber ? `Delete Task ${taskNumber}` : 'Delete task',
        action: () => toastError(inst.removeTasks([target.footprint.task])),
        variant: 'destructive'
      });
    }
    return items;
  });

  const maxHalfWidth = $derived(
    Math.max(fovWidth / 2, ...footprints.map(({ bounds }) => (bounds.maxX - bounds.minX) / 2))
  );
  const maxHalfHeight = $derived(
    Math.max(fovHeight / 2, ...footprints.map(({ bounds }) => (bounds.maxY - bounds.minY) / 2))
  );
  const marginX = $derived(Number.isFinite(maxHalfWidth) ? maxHalfWidth : 0);
  const marginY = $derived(Number.isFinite(maxHalfHeight) ? maxHalfHeight : 0);
  const viewBoxWidth = $derived(stageWidth + marginX * 2);
  const viewBoxHeight = $derived(stageHeight + marginY * 2);
  const viewBoxMinX = $derived(Math.min(0, ox * stageWidth) - marginX);
  const viewBoxMinY = $derived(Math.min(0, oy * stageHeight) - marginY);
  const viewBox = $derived(`${viewBoxMinX} ${viewBoxMinY} ${viewBoxWidth} ${viewBoxHeight}`);

  let xyContainer = $state<HTMLDivElement | null>(null);
  let zContainer = $state<HTMLDivElement | null>(null);
  let canvasWidth = $state(400);
  let canvasHeight = $state(250);
  let zWidth = $state(400);
  let zHeight = $state(250);
  const aspectRatio = $derived(viewBoxHeight > 0 ? viewBoxWidth / viewBoxHeight : 1);
  const scale = $derived(viewBoxWidth > 0 ? canvasWidth / viewBoxWidth : 1);
  const sliderWidth = 16;
  const xSliderStyle = $derived(
    `left: ${marginX * scale}px; top: ${-sliderWidth / 2}px; width: ${stageWidth * scale}px; height: ${sliderWidth}px;`
  );
  const ySliderStyle = $derived(
    `left: ${-sliderWidth / 2}px; top: ${marginY * scale}px; width: ${sliderWidth}px; height: ${stageHeight * scale}px;`
  );
  const fovExtension = $derived(scale > 0 ? sliderWidth / 2 / scale : 0);
  const fovX = $derived(sxPos - sxLower);
  const fovY = $derived(syPos - syLower);

  function fitXY(width: number, height: number): void {
    if (width <= 0 || height <= 0 || !Number.isFinite(aspectRatio) || aspectRatio <= 0) return;
    if (width / height > aspectRatio) {
      canvasHeight = height;
      canvasWidth = height * aspectRatio;
    } else {
      canvasWidth = width;
      canvasHeight = width / aspectRatio;
    }
  }

  onMount(() => {
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.target === xyContainer) fitXY(entry.contentRect.width, entry.contentRect.height);
        if (entry.target === zContainer) {
          if (entry.contentRect.width > 0) zWidth = entry.contentRect.width;
          if (entry.contentRect.height > 0) zHeight = entry.contentRect.height;
        }
      }
    });
    if (xyContainer) observer.observe(xyContainer);
    if (zContainer) observer.observe(zContainer);
    return () => observer.disconnect();
  });

  $effect(() => {
    if (aspectRatio <= 0) return;
    if (xyContainer) {
      const { width, height } = xyContainer.getBoundingClientRect();
      fitXY(width, height);
    }
  });

  const stageTarget = $derived(instrument?.stage.target ?? null);
  const targetPending = $derived(instrument?.stage.targetPending ?? false);
  const displayX = $derived(targetPending && stageTarget?.x != null ? stageTarget.x : sxPos);
  const displayY = $derived(targetPending && stageTarget?.y != null ? stageTarget.y : syPos);
  const displayZ = $derived(targetPending && stageTarget?.z != null ? stageTarget.z : zPos);
  const zLineX = $derived(stageDepth > 0 ? ((zPos - zLower) / stageDepth) * zWidth : 0);

  function sliderValue(event: Event): number {
    return Number.parseFloat((event.target as HTMLInputElement).value);
  }

  function oriented(bounds: Bounds): { x: number; y: number; width: number; height: number } {
    const x1 = ox * (bounds.minX - sxLower);
    const x2 = ox * (bounds.maxX - sxLower);
    const y1 = oy * (bounds.minY - syLower);
    const y2 = oy * (bounds.maxY - syLower);
    return { x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.abs(x2 - x1), height: Math.abs(y2 - y1) };
  }
</script>

{#snippet renderMenuItems(items: MenuItem[])}
  {#each items as item, index (index)}
    {#if item.type === 'separator'}
      <ContextMenu.Separator />
    {:else if item.type === 'submenu'}
      <ContextMenu.Sub>
        <ContextMenu.SubTrigger>{item.label}</ContextMenu.SubTrigger>
        <ContextMenu.SubContent>{@render renderMenuItems(item.items)}</ContextMenu.SubContent>
      </ContextMenu.Sub>
    {:else}
      <ContextMenu.Item onSelect={item.action} disabled={item.disabled} variant={item.variant}>
        {item.label}
      </ContextMenu.Item>
    {/if}
  {/each}
{/snippet}

<div class="flex h-full min-h-0 min-w-0 flex-col">
  <PageHeader items={[{ label: 'Grid' }]} />
  <div class="min-h-0 flex-1 overflow-hidden">
    {#if instrument}
      <div class="flex h-full min-w-0 flex-col">
        <div class="flex flex-wrap items-center gap-1 border-b border-line-muted px-3 py-2">
          {#each layerItems as { key, color, Icon, title } (key)}
            <button
              type="button"
              onclick={() => (layers[key] = !layers[key])}
              class="cursor-pointer rounded-full p-1 transition-colors {layers[key] ? color : 'text-fg-faint'}"
              {title}
            >
              <Icon width="14" height="14" />
            </button>
          {/each}
        </div>

        <div class="flex min-h-0 min-w-0 flex-1 flex-col gap-4 p-4">
          <div bind:this={xyContainer} class="grid min-h-0 min-w-0 flex-1 place-content-center">
            <div class="relative" style="width: {canvasWidth}px; height: {canvasHeight}px;">
              <p class="absolute top-1 right-1 z-20 text-fg-muted">X / Y</p>
              <input
                type="range"
                aria-label="Stage X"
                class="stage-slider absolute z-10"
                style:--thumb-length="{sliderWidth}px"
                style={xSliderStyle}
                min={sxLower}
                max={sxUpper}
                step={100}
                value={displayX}
                disabled={sxMoving}
                oninput={(event) => toastError(instrument.stage.moveTo({ x: sliderValue(event) }))}
              />
              <input
                type="range"
                aria-label="Stage Y"
                class="stage-slider {oy < 0 ? 'vertical-rtl' : 'vertical-ltr'} absolute z-10"
                style:--thumb-length="{sliderWidth}px"
                style={ySliderStyle}
                min={syLower}
                max={syUpper}
                step={100}
                value={displayY}
                disabled={syMoving}
                oninput={(event) => toastError(instrument.stage.moveTo({ y: sliderValue(event) }))}
              />

              <ContextMenu.Root>
                <ContextMenu.Trigger>
                  <svg
                    bind:this={svgRef}
                    {viewBox}
                    class="border border-line-faint"
                    style="width: {canvasWidth}px; height: {canvasHeight}px;"
                    overflow="visible"
                    role="img"
                    aria-label="XY acquisition grid"
                    oncontextmenu={handleCanvasContext}
                  >
                    {#if layers.fov}
                      <g class="pointer-events-none opacity-75">
                        <line
                          x1={viewBoxMinX - fovExtension}
                          y1={oy * fovY}
                          x2={viewBoxMinX + viewBoxWidth}
                          y2={oy * fovY}
                          vector-effect="non-scaling-stroke"
                          stroke-width="1"
                          stroke={syMoving ? 'var(--color-danger)' : 'var(--color-success)'}
                        />
                        <line
                          x1={ox * fovX}
                          y1={viewBoxMinY - fovExtension}
                          x2={ox * fovX}
                          y2={viewBoxMinY + viewBoxHeight}
                          vector-effect="non-scaling-stroke"
                          stroke-width="1"
                          stroke={sxMoving ? 'var(--color-danger)' : 'var(--color-success)'}
                        />
                      </g>
                    {/if}

                    {#if layers.grid}
                      {#each [...gridTiles].sort((a, b) => Number(tileSelected(a)) - Number(tileSelected(b))) as tile (`${tile.row}:${tile.col}`)}
                        <rect
                          x={ox * tile.x - tile.width / 2}
                          y={oy * tile.y - tile.height / 2}
                          width={tile.width}
                          height={tile.height}
                          fill="transparent"
                          stroke={tileSelected(tile) ? 'var(--color-fg)' : 'var(--color-line)'}
                          stroke-opacity={tileSelected(tile) ? 0.5 : 1}
                          stroke-width="1"
                          vector-effect="non-scaling-stroke"
                          class:cursor-pointer={!isXYMoving}
                          class:cursor-not-allowed={isXYMoving}
                          role="button"
                          tabindex={isXYMoving ? -1 : 0}
                          onclick={(event) => handleTileSelect(event, tile)}
                          oncontextmenu={() => handleTileContext(tile)}
                          onkeydown={(event) => handleKeydown(event, () => selectTiles([tile]))}
                        >
                          <title>Grid row {tile.row}, column {tile.col}</title>
                        </rect>
                      {/each}
                    {/if}

                    {#if layers.volumes}
                      {#each [...footprints].sort((a, b) => Number(a.profile === activeProfile) - Number(b.profile === activeProfile)) as footprint (footprint.key)}
                        {@const rect = oriented(footprint.bounds)}
                        {@const active = footprint.profile === activeProfile}
                        {@const selected = footprint.task === selectedTask}
                        <rect
                          x={rect.x}
                          y={rect.y}
                          width={rect.width}
                          height={rect.height}
                          fill="currentColor"
                          fill-opacity={selected ? 0.2 : active ? 0.08 : 0.025}
                          stroke="currentColor"
                          stroke-opacity={selected ? 0.65 : active ? 0.3 : 0.15}
                          stroke-width="1"
                          vector-effect="non-scaling-stroke"
                          class="text-fg outline-none"
                          class:cursor-pointer={!isXYMoving}
                          class:cursor-not-allowed={isXYMoving}
                          role="button"
                          tabindex={isXYMoving ? -1 : 0}
                          onclick={() => handleVolumeSelect(footprint)}
                          oncontextmenu={() => handleVolumeContext(footprint)}
                          onkeydown={(event) => handleKeydown(event, () => (selectedTask = footprint.task))}
                        >
                          <title
                            >Volume {footprint.order} · Task {taskNumbers.get(footprint.task) ?? '—'} · {footprint.profile}</title
                          >
                        </rect>
                      {/each}
                    {/if}

                    {#if layers.path && pathPoints.length > 1}
                      <polyline
                        fill="none"
                        stroke="currentColor"
                        stroke-opacity="0.35"
                        stroke-width="1.25"
                        vector-effect="non-scaling-stroke"
                        class="pointer-events-none text-fg-muted"
                        points={pathPoints.map(({ x, y }) => `${ox * (x - sxLower)},${oy * (y - syLower)}`).join(' ')}
                      />
                    {/if}
                  </svg>
                </ContextMenu.Trigger>
                <ContextMenu.Content class="min-w-44">{@render renderMenuItems(menuItems)}</ContextMenu.Content>
              </ContextMenu.Root>
            </div>
          </div>

          <div
            bind:this={zContainer}
            class="relative min-h-0 min-w-0 flex-1 border border-line-faint transition-colors duration-300 ease-in-out hover:bg-floating/75"
          >
            <p class="absolute top-1 right-1 z-20 text-fg-muted">Z</p>
            <input
              type="range"
              aria-label="Stage Z"
              class="stage-slider absolute inset-0 z-10 h-full w-full"
              style:--thumb-length="{zHeight}px"
              min={zLower}
              max={zUpper}
              step={10}
              value={displayZ}
              disabled={zMoving}
              oninput={(event) => toastError(instrument.stage.moveTo({ z: sliderValue(event) }))}
            />
            <svg
              viewBox="0 0 {zWidth} {zHeight}"
              class="pointer-events-none absolute inset-0"
              preserveAspectRatio="none"
              width="100%"
              height="100%"
              aria-label="Z acquisition ranges"
            >
              {#each instrument.plan as task (task.id)}
                {@const selected = task.id === selectedTask}
                {@const active = activeProfile ? task.profiles.includes(activeProfile) : false}
                {@const start = stageDepth > 0 ? ((task.z.start - zLower) / stageDepth) * zWidth : 0}
                {@const end = stageDepth > 0 ? ((task.z.end - zLower) / stageDepth) * zWidth : 0}
                <g
                  stroke="currentColor"
                  stroke-width={selected ? 1.5 : 0.5}
                  opacity={selected ? 1 : active ? 0.3 : 0.15}
                  class="text-fg"
                >
                  <line x1={start} y1="0" x2={start} y2={zHeight} vector-effect="non-scaling-stroke" />
                  <line x1={end} y1="0" x2={end} y2={zHeight} vector-effect="non-scaling-stroke" />
                </g>
              {/each}
              <line
                x1={zLineX}
                y1="0"
                x2={zLineX}
                y2={zHeight}
                vector-effect="non-scaling-stroke"
                stroke-width="1"
                stroke={zMoving ? 'var(--color-danger)' : 'var(--color-success)'}
              >
                <title>Z: {formatSpatialDistance(zPos, prefs.spatialUnit.get())}</title>
              </line>
            </svg>
          </div>
        </div>
      </div>
    {/if}
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
    &.vertical-rtl {
      writing-mode: vertical-rl;
      direction: rtl;
      --_track-bg: linear-gradient(var(--_track-color), var(--_track-color)) center / var(--_track-width) 100% no-repeat;
    }
  }
</style>
