<script lang="ts" module>
  export type MenuItem =
    | { type: 'action'; label: string; action: () => void; disabled?: boolean; variant?: 'destructive' }
    | { type: 'submenu'; label: string; items: MenuItem[]; disabled?: boolean }
    | { type: 'separator' };
</script>

<script lang="ts">
  import type { Component } from 'svelte';
  import type { Session } from '$lib/main';
  import type { LayerVisibility } from '$lib/main/types';
  import { type Tile, type Stack } from '$lib/main/types';
  import { GridLines, StackLight, ImageLight } from '$lib/icons';
  import { compositeFullFrames } from '$lib/main/preview.svelte';
  import { sanitizeString } from '$lib/utils';
  import { ContextMenu } from '$lib/ui/kit';
  import { SvelteSet } from 'svelte/reactivity';
  import { onMount } from 'svelte';
  import { watch } from 'runed';

  interface Props {
    session: Session;
    layers?: LayerVisibility;
  }

  let { session, layers = $bindable({ grid: false, stacks: true, path: true, fov: true, thumbnail: true }) }: Props =
    $props();

  const layerItems: { key: keyof LayerVisibility; color: string; Icon: Component; title: string }[] = [
    { key: 'grid', color: 'text-fg-muted', Icon: GridLines, title: 'Toggle grid' },
    { key: 'stacks', color: 'text-info', Icon: StackLight, title: 'Toggle stacks' },
    { key: 'thumbnail', color: 'text-success', Icon: ImageLight, title: 'Toggle thumbnail' }
  ];

  // ── Geometry ─────────────────────────────────────────────────────────

  let isXYMoving = $derived(session.stage.x?.isMoving || session.stage.y?.isMoving);
  let isAcquiring = $derived(session.mode === 'acquiring');

  let arrowSize = $derived(Math.min(session.fov.width, session.fov.height) * 0.08);

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
  // ViewBox: stage bounds + margin to fit current FOV and any existing stacks
  let marginX = $derived(Math.max(session.fov.width / 2, ...session.stacks.map((s) => s.w / 2)));
  let marginY = $derived(Math.max(session.fov.height / 2, ...session.stacks.map((s) => s.h / 2)));
  let viewBoxWidth = $derived(session.stage.width + marginX * 2);
  let viewBoxHeight = $derived(session.stage.height + marginY * 2);
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

  // Clear stale thumbnail when stage moves without preview running
  let shouldClearThumbnail = $derived(!session.preview?.isPreviewing && isXYMoving);
  watch(
    () => shouldClearThumbnail,
    (clear) => {
      if (clear) thumbnail = '';
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
    | { kind: 'tile'; tile: Tile; x: number; y: number }
    | { kind: 'stack'; stack: Stack; x: number; y: number }
    | { kind: 'empty'; x: number; y: number }
    | null;

  let contextTarget = $state<ContextTarget>(null);
  let clipboard = $state<{ x?: number; y?: number; zStartUm?: number; zEndUm?: number }>({});
  let svgRef = $state<SVGSVGElement | null>(null);

  /** Convert mouse event to SVG viewBox coordinates (stage-relative). */
  function svgPoint(e: MouseEvent): { x: number; y: number } | null {
    if (!svgRef) return null;
    const ctm = svgRef.getScreenCTM()?.inverse();
    if (!ctm) return null;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm);
    return { x: pt.x, y: pt.y };
  }

  function handleTileContext(e: MouseEvent, tile: Tile) {
    if (!isTileSelected(tile.row, tile.col)) selectTiles([tile]);
    session.clearStackSelection();
    const pt = svgPoint(e);
    contextTarget = { kind: 'tile', tile, x: pt?.x ?? tile.x, y: pt?.y ?? tile.y };
  }

  function handleStackContext(e: MouseEvent, stack: Stack) {
    if (!session.isStackSelected(stack.stack_id)) session.selectStacks([stack]);
    clearTileSelection();
    const pt = svgPoint(e);
    contextTarget = { kind: 'stack', stack, x: pt?.x ?? stack.x, y: pt?.y ?? stack.y };
  }

  function handleCanvasContext(e: MouseEvent) {
    if (e.target !== svgRef) return;
    const pt = svgPoint(e);
    if (!pt || !session.stage.x || !session.stage.y) return;
    contextTarget = {
      kind: 'empty',
      x: session.stage.x.lowerLimit + pt.x,
      y: session.stage.y.lowerLimit + pt.y
    };
  }

  /** Build the context menu items based on what was right-clicked. */
  const menuItems = $derived.by<MenuItem[]>(() => {
    const target = contextTarget;
    if (!target) return [];
    if (isAcquiring) return [{ type: 'action', label: 'Acquisition in progress', action: () => {}, disabled: true }];

    const items: MenuItem[] = [];
    const lx = session.stage.x?.lowerLimit ?? 0;
    const ly = session.stage.y?.lowerLimit ?? 0;

    // ── Move here (all targets) ──
    const moveAction = () => {
      if (target.kind === 'empty') {
        targetX = target.x;
        targetY = target.y;
        session.stage.moveXY(target.x, target.y);
      } else if (target.kind === 'tile') {
        moveToTilePosition(target.tile.x, target.tile.y);
      } else {
        moveToTilePosition(target.stack.x, target.stack.y);
      }
    };
    items.push({ type: 'action', label: 'Move here', action: moveAction, disabled: isXYMoving });

    // ── Select tiles (tile targets only) ──
    if (target.kind === 'tile') {
      const tile = target.tile;
      items.push({
        type: 'submenu',
        label: 'Select tiles',
        items: [
          {
            type: 'action',
            label: `Row ${tile.row}`,
            action: () => selectTiles(session.tiles.filter((t) => t.row === tile.row))
          },
          {
            type: 'action',
            label: `Column ${tile.col}`,
            action: () => selectTiles(session.tiles.filter((t) => t.col === tile.col))
          },
          { type: 'separator' },
          { type: 'action', label: 'All', action: () => selectTiles(session.tiles) },
          {
            type: 'action',
            label: 'Invert',
            action: () => selectTiles(session.tiles.filter((t) => !isTileSelected(t.row, t.col)))
          }
        ]
      });
      items.push({
        type: 'action',
        label: 'Copy X',
        action: () => {
          clipboard = { ...clipboard, x: tile.x };
        }
      });
      items.push({
        type: 'action',
        label: 'Copy Y',
        action: () => {
          clipboard = { ...clipboard, y: tile.y };
        }
      });
    }

    // ── Select stacks (stack targets only) ──
    if (target.kind === 'stack') {
      const stack = target.stack;
      const profileLabel = sanitizeString(stack.profile_id);
      items.push({
        type: 'submenu',
        label: 'Select stacks',
        items: [
          { type: 'action', label: 'All', action: () => session.selectMultipleStacks() },
          {
            type: 'action',
            label: profileLabel,
            action: () => session.selectMultipleStacks({ profileIds: [stack.profile_id] })
          }
        ]
      });
    }

    // ── Align grid (empty canvas and stacks only — tiles ARE the grid) ──
    if (target.kind !== 'tile') {
      const pos =
        target.kind === 'empty' ? { x: target.x, y: target.y } : { x: lx + target.stack.x, y: ly + target.stack.y };
      items.push({
        type: 'submenu',
        label: 'Align grid',
        disabled: !session.gridConfig,
        items: [
          { type: 'action', label: 'Top', action: () => session.alignGrid('top', pos) },
          { type: 'action', label: 'Bottom', action: () => session.alignGrid('bottom', pos) },
          { type: 'action', label: 'Left', action: () => session.alignGrid('left', pos) },
          { type: 'action', label: 'Right', action: () => session.alignGrid('right', pos) },
          { type: 'separator' },
          { type: 'action', label: 'Center', action: () => session.alignGrid('center', pos) }
        ]
      });
    }

    // ── Add stack ──
    if (target.kind === 'empty') {
      // Copy position from clicked point (stage-relative)
      const clickX = target.x - lx;
      const clickY = target.y - ly;
      items.push({
        type: 'action',
        label: 'Copy X',
        action: () => {
          clipboard = { ...clipboard, x: clickX };
        }
      });
      items.push({
        type: 'action',
        label: 'Copy Y',
        action: () => {
          clipboard = { ...clipboard, y: clickY };
        }
      });
      // Add stack at clicked position for active profile
      items.push({ type: 'separator' });
      items.push({
        type: 'action',
        label: 'Add stack',
        action: () => {
          session.addStacks([
            {
              x: target.x - lx,
              y: target.y - ly,
              zStartUm: session.acq.default_z_start,
              zEndUm: session.acq.default_z_end
            }
          ]);
        }
      });
    } else if (target.kind === 'tile') {
      const emptyCount = selectedTilesList.filter((t) => !session.getStackAtPosition(t.x, t.y)).length;
      if (emptyCount > 0) {
        items.push({ type: 'separator' });
        items.push({
          type: 'action',
          label: emptyCount === 1 ? 'Add stack' : `Add stacks (${emptyCount})`,
          action: () => {
            const tiles = selectedTilesList.filter((t) => !session.getStackAtPosition(t.x, t.y));
            session.addStacks(
              tiles.map((t) => ({
                x: t.x,
                y: t.y,
                zStartUm: session.acq.default_z_start,
                zEndUm: session.acq.default_z_end
              }))
            );
          }
        });
      }
    }

    // ── Z range, Add for active profile, Delete (stack targets only) ──
    if (target.kind === 'stack') {
      const stack = target.stack;
      const selectedCount = session.selectedStacks.length;
      const isSingle = selectedCount <= 1;
      const isOtherProfile = stack.profile_id !== session.activeProfileId;
      const isPlanned = session.selectedStacks.some((s) => s.status === 'planned');
      const canDelete = isSingle
        ? stack.status === 'planned' || stack.status === 'skipped'
        : session.selectedStacks.some((s) => s.status === 'planned' || s.status === 'skipped');
      const plannedTargets = () => (isSingle ? [stack] : session.selectedStacks.filter((s) => s.status === 'planned'));

      items.push({ type: 'separator' });

      // Copy (single stack only)
      if (isSingle) {
        items.push({
          type: 'action',
          label: 'Copy X',
          action: () => {
            clipboard = { ...clipboard, x: stack.x };
          }
        });
        items.push({
          type: 'action',
          label: 'Copy Y',
          action: () => {
            clipboard = { ...clipboard, y: stack.y };
          }
        });
        items.push({
          type: 'action',
          label: 'Copy Z range',
          action: () => {
            clipboard = { ...clipboard, zStartUm: stack.z_start, zEndUm: stack.z_end };
          }
        });
      }

      // Paste
      if (clipboard.x !== undefined && isPlanned) {
        items.push({
          type: 'action',
          label: isSingle ? 'Paste X' : `Paste X (${selectedCount})`,
          action: () => session.editStacks(plannedTargets().map((s) => ({ stackId: s.stack_id, x: clipboard.x })))
        });
      }
      if (clipboard.y !== undefined && isPlanned) {
        items.push({
          type: 'action',
          label: isSingle ? 'Paste Y' : `Paste Y (${selectedCount})`,
          action: () => session.editStacks(plannedTargets().map((s) => ({ stackId: s.stack_id, y: clipboard.y })))
        });
      }
      if (clipboard.zStartUm !== undefined && clipboard.zEndUm !== undefined && isPlanned) {
        items.push({
          type: 'action',
          label: isSingle ? 'Paste Z range' : `Paste Z range (${selectedCount})`,
          action: () =>
            session.editStacks(
              plannedTargets().map((s) => ({
                stackId: s.stack_id,
                zStartUm: clipboard.zStartUm,
                zEndUm: clipboard.zEndUm
              }))
            )
        });
      }

      // Add stack(s) for active profile (other-profile stacks only)
      if (isOtherProfile) {
        const otherStacks = (isSingle ? [stack] : session.selectedStacks).filter(
          (s) => s.profile_id !== session.activeProfileId && !session.getStackAtPosition(s.x, s.y)
        );
        if (otherStacks.length > 0) {
          items.push({
            type: 'action',
            label: otherStacks.length === 1 ? 'Add stack' : `Add stacks (${otherStacks.length})`,
            action: () => {
              session.addStacks(
                otherStacks.map((s) => ({
                  x: s.x,
                  y: s.y,
                  zStartUm: session.acq.default_z_start,
                  zEndUm: session.acq.default_z_end
                }))
              );
            }
          });
        }
      }

      // Delete
      if (canDelete) {
        const deletable = isSingle
          ? [stack]
          : session.selectedStacks.filter((s) => s.status === 'planned' || s.status === 'skipped');
        items.push({
          type: 'action',
          label: isSingle ? 'Delete stack' : `Delete stacks (${deletable.length})`,
          variant: 'destructive',
          action: () => session.removeStacks(deletable.map((s) => s.stack_id))
        });
      }
    }

    return items;
  });
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
  <g class="pointer-events-none opacity-75">
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
{#snippet stackRect(stack: Stack, isActive: boolean)}
  {@const selected = session.isStackSelected(stack.stack_id)}
  {@const w = stack.w}
  {@const h = stack.h}
  <rect
    x={stack.x - w / 2}
    y={stack.y - h / 2}
    width={w}
    height={h}
    data-stack-status={stack.status}
    class="nss text-(--stack-status) outline-none"
    fill={isActive ? 'currentColor' : 'transparent'}
    fill-opacity={isActive ? (selected ? '0.5' : '0.15') : '0'}
    stroke="currentColor"
    stroke-opacity={selected ? '0.9' : isActive ? '0.25' : '0.4'}
    stroke-width="1"
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
{/snippet}

{#snippet inactiveStacksLayer()}
  {#if layers.stacks}
    <g>
      {#each session.inactiveStacks as stack (stack.stack_id)}
        {@render stackRect(stack, false)}
      {/each}
    </g>
  {/if}
{/snippet}

{#snippet activeStacksLayer()}
  {#if layers.stacks}
    {@const points = session.stacks.filter((s) => s.status !== 'completed').map((s) => ({ x: s.x, y: s.y }))}
    <g>
      {#each session.activeStacks as stack (stack.stack_id)}
        {@render stackRect(stack, true)}
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
        {@const dist = Math.hypot(p2.x - p1.x, p2.y - p1.y)}
        {#if dist > arrowSize}
          {@const midX = (p1.x + p2.x) / 2}
          {@const midY = (p1.y + p2.y) / 2}
          {@const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x) * (180 / Math.PI)}
          <path
            d="M {-arrowSize * 0.5} {-arrowSize * 0.6} L {arrowSize * 0.5} 0 L {-arrowSize * 0.5} {arrowSize * 0.6}"
            stroke-width={arrowSize * 0.15}
            class="fill-none opacity-70"
            transform="translate({midX}, {midY}) rotate({angle})"
          />
        {:else if dist < 1}
          <!-- Overlapping stacks: show dot marker -->
          <circle cx={p1.x} cy={p1.y} r={arrowSize * 0.25} class="fill-current opacity-50" stroke="none" />
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
          {@render inactiveStacksLayer()}
          {@render activeStacksLayer()}
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
