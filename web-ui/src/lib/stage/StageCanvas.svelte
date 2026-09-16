<script module lang="ts">
  import type Konva from 'konva';
  import type { Snippet } from 'svelte';

  import type { MenuSelection } from './context.svelte';
  import type { Bounds, Orientation, Point, Viewport, ViewTransform } from './geometry';

  export interface StageCanvasProps {
    bounds: Bounds;
    orientation?: Orientation;
    maxScale?: number;
    viewport?: Viewport | null;
    marquee?: Bounds | null;
    children?: Snippet;
    menu?: Snippet<
      [MenuSelection, Snippet, (point: Point) => void, (bounds: Bounds) => void, (point: Point | null) => void]
    >;
    overlay?: Snippet<[ViewTransform, number, Point | null]>;
    resolveDestination?: (point: Point, hits: Konva.Shape[]) => Point | undefined;
  }
</script>

<script lang="ts">
  import { onMount } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';
  import { Group, Layer, Rect, Stage } from 'svelte-konva';

  import { browser } from '$app/environment';
  import { Close, FitToScreen, Layers } from '$lib/icons';
  import { ContextMenu } from '$lib/kit';
  import { watchTheme } from '$lib/themes/manager.svelte';

  import { provideStageContext, type StageFeature } from './context.svelte';
  import { box, fit, intersect, project, screenRect, screenTransform, unproject, worldTransform } from './geometry';

  let {
    bounds,
    orientation = { x: 1, y: 1 },
    maxScale = 7,
    viewport = $bindable(null),
    marquee = $bindable(null),
    children,
    menu,
    overlay,
    resolveDestination
  }: StageCanvasProps = $props();

  let host: HTMLDivElement;
  let stage = $state<Stage>();
  let width = $state(0);
  let height = $state(0);
  let cursor = $state.raw<Point | null>(null);
  let altHeld = $state(false);
  let dragging = $state.raw<Konva.Node | null>(null);
  let selectionStart = $state<Point | null>(null);
  let selectionPointer: number | null = null;
  let selectionOrigin: Point | null = null;
  let selectionMoved = false;
  const features = new SvelteMap<string, StageFeature>();
  let menuOpen = $state(false);
  let menuSelection = $state.raw<MenuSelection | null>(null);
  let menuPreview = $state.raw<Point | null>(null);
  let borderColor = $state('#52525b');
  let selectionColor = $state('#e5e7eb');

  const valid = $derived(
    width > 0 &&
      height > 0 &&
      bounds.maxX > bounds.minX &&
      bounds.maxY > bounds.minY &&
      Object.values(bounds).every(Number.isFinite) &&
      Number.isFinite(maxScale) &&
      maxScale > 0
  );
  const fitted = $derived(valid ? fit(bounds, width, height, maxScale) : { cx: 0, cy: 0, scale: 1 });
  $effect(() => {
    if (!valid || viewport !== null) return;
    const initial = fitted;
    // Allow pane layout and ResizeObserver measurements to settle before saving the initial fit.
    let frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => (viewport = initial));
    });
    return () => cancelAnimationFrame(frame);
  });

  const view = $derived.by(() => {
    if (!valid) return { x: 0, y: 0, scale: 1 };
    const { cx, cy, scale } = viewport ?? fitted;
    const x = width / 2 - cx * scale * orientation.x;
    const y = height / 2 + cy * scale * orientation.y;
    return { ...limitPan(x, y, scale), scale };
  });
  const measuredView = $derived({ ...view, width, height });
  const visibleBounds = $derived(
    intersect(
      bounds,
      box(unproject({ x: 0, y: 0 }, view, orientation), unproject({ x: width, y: height }, view, orientation))
    )
  );
  const menuSections = $derived.by(() => {
    const selection = menuSelection;
    if (!selection) return [];
    return [...features.values()]
      .filter((feature) => feature.visible)
      .flatMap((feature) => {
        const content = feature.menu?.(selection);
        return content ? [{ id: feature.id, label: feature.label, content }] : [];
      });
  });

  function center(point: Point) {
    const screen = project(point, view, orientation);
    setView(view.x + width / 2 - screen.x, view.y + height / 2 - screen.y, view.scale);
  }

  function fitBounds(target: Bounds) {
    if (
      !valid ||
      target.maxX <= target.minX ||
      target.maxY <= target.minY ||
      !Object.values(target).every(Number.isFinite)
    )
      return;
    viewport = fit(target, width, height, maxScale);
  }

  provideStageContext({
    get bounds() {
      return bounds;
    },
    get orientation() {
      return orientation;
    },
    get view() {
      return measuredView;
    },
    get visibleBounds() {
      return visibleBounds;
    },
    get marquee() {
      return marquee;
    },
    get selecting() {
      return selectionStart !== null;
    },
    get altHeld() {
      return altHeld;
    },
    get cursor() {
      return cursor;
    },
    get menuSelection() {
      return menuSelection;
    },
    get menuPreview() {
      return menuPreview;
    },
    get interactionEnabled() {
      return !altHeld && !selectionStart && !menuOpen;
    },
    project: (point) => project(point, view, orientation),
    unproject: (point) => unproject(point, view, orientation),
    register(feature) {
      if (features.has(feature.id)) throw new Error('Duplicate stage feature: ' + feature.id);
      features.set(feature.id, feature);
      return () => {
        features.delete(feature.id);
      };
    }
  });

  function eventPoint(event: MouseEvent): Point {
    const rect = host.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function limitPan(x: number, y: number, scale: number) {
    const frame = screenRect(bounds, { x, y, scale }, orientation);
    const clamp = (start: number, extent: number, size: number) => {
      if (extent <= size) return (size - extent) / 2 - start;
      const slack = (size / 3) * (1 - size / extent);
      return Math.max(size - extent - slack, Math.min(start, slack)) - start;
    };
    return { x: x + clamp(frame.x, frame.width, width), y: y + clamp(frame.y, frame.height, height) };
  }

  function pan(event: Konva.KonvaEventObject<MouseEvent | PointerEvent | TouchEvent>) {
    if (event.target !== stage?.node) return;
    event.target.position(setView(event.target.x(), event.target.y(), view.scale));
  }

  function setView(x: number, y: number, scale: number) {
    const next = { ...limitPan(x, y, scale), scale };
    const center = unproject({ x: width / 2, y: height / 2 }, next, orientation);
    viewport = { cx: center.x, cy: center.y, scale };
    return next;
  }

  function zoom(event: Konva.KonvaEventObject<WheelEvent>) {
    event.evt.preventDefault();
    if (dragging || selectionStart || menuOpen) return;
    const screen = eventPoint(event.evt);
    const world = unproject(screen, view, orientation);
    const delta = event.evt.deltaY * (event.evt.deltaMode === 1 ? 16 : event.evt.deltaMode === 2 ? height : 1);
    const scale = Math.max(fitted.scale, Math.min(maxScale, view.scale * Math.exp(-delta * 0.0015)));
    const x = screen.x - world.x * scale * orientation.x;
    const y = screen.y + world.y * scale * orientation.y;
    setView(x, y, scale);
  }

  function beginSelection(event: Konva.KonvaEventObject<PointerEvent>) {
    if (!stage || event.evt.button !== 0 || dragging || menuOpen) return;
    if (!event.evt.altKey) return;
    stage.node.container().style.cursor = 'crosshair';
    stage.node.draggable(false);
    selectionPointer = event.evt.pointerId;
    selectionOrigin = eventPoint(event.evt);
    selectionStart = unproject(selectionOrigin, view, orientation);
    selectionMoved = false;
  }

  function updateSelection(event: PointerEvent) {
    if (!selectionStart || !selectionOrigin || event.pointerId !== selectionPointer) return;
    const point = eventPoint(event);
    if (!selectionMoved && Math.hypot(point.x - selectionOrigin.x, point.y - selectionOrigin.y) <= 4) return;
    selectionMoved = true;
    marquee = box(selectionStart, unproject(point, view, orientation));
  }

  function finishSelection(event?: PointerEvent) {
    if (event && event.button !== 0) return;
    if (!selectionStart || (event && event.pointerId !== selectionPointer)) return;
    if (stage) stage.node.container().style.cursor = 'grab';
    if (event) updateSelection(event);
    if (!selectionMoved) marquee = null;
    selectionStart = null;
    selectionPointer = null;
    selectionOrigin = null;
    stage?.node.draggable(!altHeld && !menuOpen);
  }

  function cancelSelection() {
    if (!selectionStart) return;
    marquee = null;
    finishSelection();
  }

  function openMenu(event: Konva.KonvaEventObject<PointerEvent>) {
    if (!stage) return;
    menuPreview = null;
    const screen = eventPoint(event.evt);
    const world = unproject(screen, view, orientation);
    if (
      marquee &&
      world.x >= marquee.minX &&
      world.x <= marquee.maxX &&
      world.y >= marquee.minY &&
      world.y <= marquee.maxY
    ) {
      menuSelection = { bounds: { ...marquee } };
    } else {
      marquee = null;
      const hits = stage.node.getAllIntersections(screen).sort((a, b) => b.getAbsoluteZIndex() - a.getAbsoluteZIndex());
      menuSelection = {
        point: world,
        destination: resolveDestination?.(world, hits),
        hits
      };
    }
  }

  $effect(() => {
    if (!menuOpen) {
      menuSelection = null;
      menuPreview = null;
    }
  });

  watchTheme(() => {
    const style = getComputedStyle(host);
    borderColor = style.getPropertyValue('--color-line').trim() || borderColor;
    selectionColor = style.getPropertyValue('--color-fg').trim() || selectionColor;
  });

  onMount(() => {
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Alt') altHeld = true;
      if (event.key === 'Escape') {
        cancelSelection();
        marquee = null;
      }
    };
    const keyup = (event: KeyboardEvent) => {
      if (event.key === 'Alt') altHeld = false;
    };
    const blur = () => {
      altHeld = false;
      cancelSelection();
      stage?.node.stopDrag();
    };
    window.addEventListener('keydown', keydown);
    window.addEventListener('keyup', keyup);
    window.addEventListener('blur', blur);
    window.addEventListener('pointermove', updateSelection);
    window.addEventListener('pointerup', finishSelection);
    window.addEventListener('pointercancel', cancelSelection);
    return () => {
      window.removeEventListener('keydown', keydown);
      window.removeEventListener('keyup', keyup);
      window.removeEventListener('blur', blur);
      window.removeEventListener('pointermove', updateSelection);
      window.removeEventListener('pointerup', finishSelection);
      window.removeEventListener('pointercancel', cancelSelection);
    };
  });
</script>

<ContextMenu.Root bind:open={menuOpen}>
  <ContextMenu.Trigger>
    {#snippet child({ props })}
      <div
        {...props}
        bind:this={host}
        bind:clientWidth={width}
        bind:clientHeight={height}
        class="relative h-full min-h-0 w-full min-w-0 touch-none overflow-hidden bg-canvas"
        onpointermove={(event) => (cursor = unproject(eventPoint(event), view, orientation))}
        onpointerleave={() => (cursor = null)}
      >
        {#if browser && valid}
          <Stage
            bind:this={stage}
            {width}
            {height}
            x={view.x}
            y={view.y}
            divWrapperProps={{ style: 'cursor: grab' }}
            draggable={!altHeld && !selectionStart && !menuOpen}
            dragDistance={4}
            ondragmove={pan}
            ondragstart={(event) => {
              dragging = event.target;
              if (event.target === stage?.node) stage.node.container().style.cursor = 'grabbing';
            }}
            ondragend={(event) => {
              pan(event);
              dragging = null;
              if (event.target === stage?.node) stage.node.container().style.cursor = 'grab';
            }}
            onwheel={zoom}
            onpointerdown={beginSelection}
            oncontextmenu={openMenu}
            onpointerclick={(event) => {
              if (event.evt.button === 0 && !event.evt.altKey && !selectionStart) marquee = null;
            }}
          >
            <Layer>
              <Group {...worldTransform(view.scale, orientation)}>
                <Rect
                  x={bounds.minX}
                  y={bounds.minY}
                  width={bounds.maxX - bounds.minX}
                  height={bounds.maxY - bounds.minY}
                  stroke={borderColor}
                  strokeWidth={1}
                  strokeScaleEnabled={false}
                  listening={false}
                />
              </Group>
              {@render children?.()}
            </Layer>
            <Layer {...screenTransform(view)} listening={false}>
              {#if marquee}
                <Rect {...screenRect(marquee, view, orientation)} fill={selectionColor} opacity={0.08} />
                <Rect
                  {...screenRect(marquee, view, orientation)}
                  stroke={selectionColor}
                  strokeWidth={1}
                  dash={[4, 3]}
                />
              {/if}
            </Layer>
          </Stage>
          {@render overlay?.(view, width, cursor)}
        {/if}
      </div>
    {/snippet}
  </ContextMenu.Trigger>
  <ContextMenu.Content class="min-w-44">
    {#if features.size}
      <ContextMenu.Sub>
        <ContextMenu.SubTrigger>
          <Layers width="14" height="14" />
          Layers
        </ContextMenu.SubTrigger>
        <ContextMenu.SubContent class="min-w-44" sideOffset={8}>
          {#each [...features.values()].sort((a, b) => (a.menuOrder ?? 0) - (b.menuOrder ?? 0)) as feature (feature.id)}
            <ContextMenu.CheckboxItem
              checked={feature.visible}
              closeOnSelect={false}
              onCheckedChange={(visible) => feature.setVisible(visible)}
            >
              {feature.label}
            </ContextMenu.CheckboxItem>
          {/each}
        </ContextMenu.SubContent>
      </ContextMenu.Sub>
      <ContextMenu.Separator />
    {/if}
    {#if menuSelection}
      {#if 'bounds' in menuSelection}
        {@render featureMenus(menuSelection)}
        {#if menuSections.length}<ContextMenu.Separator />{/if}
        {@render mainMenu(menuSelection)}
      {:else}
        {@render mainMenu(menuSelection)}
        {#if menuSections.length}<ContextMenu.Separator />{/if}
        {@render featureMenus(menuSelection)}
      {/if}
    {/if}
  </ContextMenu.Content>
</ContextMenu.Root>

{#snippet defaultMenu()}
  {#if menuSelection && 'bounds' in menuSelection}
    {@const selectedBounds = menuSelection.bounds}
    <ContextMenu.Item onSelect={() => fitBounds(selectedBounds)}>
      <FitToScreen width="14" height="14" />
      Fit to selection
    </ContextMenu.Item>
    <ContextMenu.Item onSelect={() => (marquee = null)}>
      <Close width="14" height="14" />
      Clear selection
    </ContextMenu.Item>
  {:else}
    <ContextMenu.Item onSelect={() => (viewport = fitted)}>
      <FitToScreen width="14" height="14" />
      Fit to stage
    </ContextMenu.Item>
  {/if}
{/snippet}

{#snippet mainMenu(selection: MenuSelection)}
  {#if menu}
    {@render menu(selection, defaultMenu, center, fitBounds, (point) => (menuPreview = point))}
  {:else}
    {@render defaultMenu()}
  {/if}
{/snippet}

{#snippet featureMenus(selection: MenuSelection)}
  {#each menuSections as section, index (section.id)}
    {#if menuSections.length > 2}
      <ContextMenu.Sub>
        <ContextMenu.SubTrigger>{section.label}</ContextMenu.SubTrigger>
        <ContextMenu.SubContent class="min-w-44" sideOffset={8}>
          {@render section.content(selection)}
        </ContextMenu.SubContent>
      </ContextMenu.Sub>
    {:else}
      {#if index > 0}<ContextMenu.Separator />{/if}
      <ContextMenu.Group>
        <ContextMenu.GroupHeading>{section.label}</ContextMenu.GroupHeading>
        {@render section.content(selection)}
      </ContextMenu.Group>
    {/if}
  {/each}
{/snippet}
