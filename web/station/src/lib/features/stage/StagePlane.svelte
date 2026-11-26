<script module lang="ts">
  import type { Snippet } from 'svelte';

  import type { FitTarget, MenuSelection, NavigationTarget } from './context';
  import type { Bounds, Point, Viewport, ViewTransform } from './geometry';

  /** The map's actions for its menu: center on a point, fit a box, and show where a menu item would move the stage. */
  export interface PlaneActions {
    center(point: Point): void;
    fit(bounds: Bounds): void;
    preview(point: Point | null): void;
  }

  /** What the parts on the plane offer the menu at its selection. */
  export interface MenuTargets {
    addTask: NavigationTarget[];
    goTo: NavigationTarget[];
    fit: FitTarget[];
  }
</script>

<script lang="ts">
  import type Konva from 'konva';
  import { onMount } from 'svelte';
  import { Group, Layer, Rect, Stage } from 'svelte-konva';
  import { SvelteMap } from 'svelte/reactivity';

  import { browser } from '$app/environment';
  import { ContextMenu } from '@voxel/kit';
  import { hexWithAlpha, toHex } from '@voxel/kit/colors';
  import { watchTheme } from '@voxel/kit/style';

  import { Plane, type PlaneColors, type StageChoice, type StageFeature, type StageMenuSource } from './context';
  import { Geometry } from './geometry';
  import Marquee from './Marquee.svelte';

  interface Props {
    /** Where the stage can go on the 2 axes: the reach of a frame's center. */
    travel: Bounds;
    /** Half of 1 frame on each axis, in µm: a band this wide around the travel is where only frame edges reach. */
    reach?: { width: number; height: number };
    /** Where the specimen can be imaged; the travel when the rig names no range. */
    specimen: Bounds;
    /** What the first view fits. */
    home: Bounds;
    maxScale?: number;
    viewport?: Viewport | null;
    marquee?: Bounds | null;
    children?: Snippet;
    menu?: Snippet<[MenuSelection, MenuTargets, PlaneActions]>;
    overlay?: Snippet<[ViewTransform, number, number, Point | null, PlaneActions]>;
    onclick?: (point: Point, names: string[], screen: Point) => void;
    onescape?: () => void;
  }

  let {
    travel,
    reach = { width: 0, height: 0 },
    specimen,
    home,
    maxScale = 7,
    viewport = $bindable(null),
    marquee = $bindable(null),
    children,
    menu,
    overlay,
    onclick,
    onescape
  }: Props = $props();

  let host: HTMLDivElement;
  let stage = $state<Stage>();
  let width = $state(0);
  let height = $state(0);
  let cursor = $state.raw<Point | null>(null);
  let altDown = $state(false);
  // Alt acts only while the pointer is over the plane, so Alt elsewhere, such as on a number box, does nothing here.
  const altHeld = $derived(altDown && cursor !== null);
  let dragging = $state.raw<Konva.Node | null>(null);
  let selectionStart = $state<Point | null>(null);
  let selectionPointer: number | null = null;
  let selectionOrigin: Point | null = null;
  let selectionMoved = false;
  let menuOpen = $state(false);
  let menuSelection = $state.raw<MenuSelection | null>(null);
  const features = new SvelteMap<string, StageFeature>();
  const sortedFeatures = $derived([...features.values()].sort((a, b) => (a.menuOrder ?? 0) - (b.menuOrder ?? 0)));
  const layered = $derived(sortedFeatures.filter((feature) => !('choices' in feature && feature.submenu)));
  const own = $derived(
    sortedFeatures.filter((feature): feature is StageChoice => 'choices' in feature && !!feature.submenu)
  );
  const menuSources = new SvelteMap<string, StageMenuSource>();
  const targets = $derived.by((): MenuTargets => {
    const selection = menuSelection;
    const sources = [...menuSources.values()];
    return {
      addTask: selection ? sources.flatMap((source) => source.addTask?.(selection) ?? []) : [],
      goTo: selection ? sources.flatMap((source) => source.goTo?.(selection) ?? []) : [],
      fit: selection ? sources.flatMap((source) => source.fit?.(selection) ?? []) : []
    };
  });
  let menuPreview = $state.raw<Point | null>(null);
  let colors = $state<PlaneColors>({
    pane: '#efede8',
    fg: '#292722',
    fgMuted: '#6b6560',
    fgFaint: '#8a847e',
    line: '#29272268',
    lineMuted: '#29272253',
    lineFaint: '#29272234',
    accent: '#2f6fd0',
    floating: '#ffffff',
    marks: '#292722',
    zones: ['#0369a1', '#945600', '#7e22ce', '#007353'],
    success: '#1a7f37',
    warning: '#9a6700'
  });

  const valid = $derived(
    width > 0 &&
      height > 0 &&
      [travel, specimen, home].every(
        (b) => Object.values(b).every(Number.isFinite) && b.maxX >= b.minX && b.maxY >= b.minY
      )
  );
  const fitted = $derived(valid ? Geometry.fit(home, width, height, maxScale) : { cx: 0, cy: 0, scale: 1 });
  // What a camera can image: the travel grown by half a frame.
  const imaged = $derived({
    minX: travel.minX - reach.width,
    maxX: travel.maxX + reach.width,
    minY: travel.minY - reach.height,
    maxY: travel.maxY + reach.height
  });
  const minScale = $derived(valid ? Math.min(fitted.scale, Geometry.fit(imaged, width, height, maxScale).scale) : 1);
  const view = $derived.by(() => {
    if (!valid) return { x: 0, y: 0, scale: 1 };
    const { cx, cy, scale } = viewport ?? fitted;
    return { ...limitPan(width / 2 - cx * scale, height / 2 + cy * scale, scale), scale };
  });
  const measuredView = $derived({ ...view, width, height });
  const visibleBounds = $derived(
    Geometry.box(Geometry.unproject({ x: 0, y: 0 }, view), Geometry.unproject({ x: width, y: height }, view))
  );
  const actions: PlaneActions = {
    center: (point) => {
      const screen = Geometry.project(point, view);
      setView(view.x + width / 2 - screen.x, view.y + height / 2 - screen.y, view.scale);
    },
    fit: (bounds) => {
      if (!valid || !Object.values(bounds).every(Number.isFinite)) return;
      const pad = Math.max(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY) * 0.04;
      viewport = Geometry.fit(bounds, width, height, maxScale, pad);
    },
    preview: (point) => (menuPreview = point)
  };

  export function center(point: Point): void {
    actions.center(point);
  }

  Plane.provide({
    get colors() {
      return colors;
    },
    get bounds() {
      return travel;
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
    project: (point) => Geometry.project(point, view),
    unproject: (point) => Geometry.unproject(point, view),
    fromClient: (clientX, clientY) => {
      const rect = host.getBoundingClientRect();
      return Geometry.unproject({ x: clientX - rect.left, y: clientY - rect.top }, view);
    },
    setCursor: (value) => {
      const container = stage?.node.container();
      if (container) container.style.cursor = value;
    },
    register(feature) {
      features.set(feature.id, feature);
      return () => features.delete(feature.id);
    },
    registerMenuSource(source) {
      menuSources.set(source.id, source);
      return () => menuSources.delete(source.id);
    }
  });

  function eventPoint(event: MouseEvent): Point {
    const rect = host.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  // The travel stays on the canvas, with a third of the canvas as slack past each edge.
  function limitPan(x: number, y: number, scale: number) {
    const frame = Geometry.screenRect(Geometry.union([imaged, home]) ?? imaged, { x, y, scale });
    const clamp = (start: number, extent: number, size: number) => {
      if (extent <= size) return (size - extent) / 2 - start;
      const slack = (size / 3) * (1 - size / extent);
      return Math.max(size - extent - slack, Math.min(start, slack)) - start;
    };
    return { x: x + clamp(frame.x, frame.width, width), y: y + clamp(frame.y, frame.height, height) };
  }

  function setView(x: number, y: number, scale: number) {
    const next = { ...limitPan(x, y, scale), scale };
    const middle = Geometry.unproject({ x: width / 2, y: height / 2 }, next);
    viewport = { cx: middle.x, cy: middle.y, scale };
    return next;
  }

  function pan(event: Konva.KonvaEventObject<MouseEvent | PointerEvent | TouchEvent>) {
    if (event.target !== stage?.node) return;
    event.target.position(setView(event.target.x(), event.target.y(), view.scale));
  }

  function zoom(event: Konva.KonvaEventObject<WheelEvent>) {
    event.evt.preventDefault();
    if (dragging || selectionStart || menuOpen) return;
    const screen = eventPoint(event.evt);
    const world = Geometry.unproject(screen, view);
    const delta = event.evt.deltaY * (event.evt.deltaMode === 1 ? 16 : event.evt.deltaMode === 2 ? height : 1);
    const scale = Math.max(minScale, Math.min(maxScale, view.scale * Math.exp(-delta * 0.0015)));
    setView(screen.x - world.x * scale, screen.y + world.y * scale, scale);
  }

  function names(screen: Point): string[] {
    const hits = stage?.node.getAllIntersections(screen) ?? [];
    return hits.sort((a, b) => b.getAbsoluteZIndex() - a.getAbsoluteZIndex()).flatMap((hit) => hit.name().split(/\s+/));
  }

  function beginSelection(event: Konva.KonvaEventObject<PointerEvent>) {
    if (!stage || event.evt.button !== 0 || dragging || menuOpen || !event.evt.altKey) return;
    stage.node.container().style.cursor = 'crosshair';
    stage.node.draggable(false);
    selectionPointer = event.evt.pointerId;
    selectionOrigin = eventPoint(event.evt);
    selectionStart = Geometry.unproject(selectionOrigin, view);
    selectionMoved = false;
  }

  function updateSelection(event: PointerEvent) {
    if (!selectionStart || !selectionOrigin || event.pointerId !== selectionPointer) return;
    const point = eventPoint(event);
    if (!selectionMoved && Math.hypot(point.x - selectionOrigin.x, point.y - selectionOrigin.y) <= 4) return;
    selectionMoved = true;
    marquee = Geometry.box(selectionStart, Geometry.unproject(point, view));
  }

  function finishSelection(event?: PointerEvent) {
    if (event && event.button !== 0) return;
    if (!selectionStart || (event && event.pointerId !== selectionPointer)) return;
    if (stage) stage.node.container().style.cursor = 'grab';
    if (event) updateSelection(event);
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

  $effect(() => {
    if (!menuOpen) {
      menuSelection = null;
      menuPreview = null;
    }
  });

  watchTheme(() => {
    const styles = getComputedStyle(host);
    const read = (name: string) => toHex(styles.getPropertyValue(name).trim() || '#000');
    colors = {
      pane: read('--pane'),
      fg: read('--fg'),
      fgMuted: read('--fg-muted'),
      fgFaint: read('--fg-faint'),
      line: styles.getPropertyValue('--line').trim(),
      lineMuted: styles.getPropertyValue('--line-muted').trim(),
      lineFaint: styles.getPropertyValue('--line-faint').trim(),
      accent: read('--accent-fg'),
      floating: read('--floating'),
      marks: read('--stage-markers'),
      zones: [1, 2, 3, 4].map((n) => read(`--stage-zone-${n}`)),
      success: read('--success-fg'),
      warning: read('--warning-fg')
    };
  });

  onMount(() => {
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Alt') altDown = true;
      if (event.key === 'Escape' && !(event.target instanceof HTMLInputElement)) {
        cancelSelection();
        marquee = null;
        onescape?.();
      }
    };
    const keyup = (event: KeyboardEvent) => {
      if (event.key === 'Alt') altDown = false;
    };
    const blur = () => {
      altDown = false;
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

{#snippet choices(feature: StageChoice)}
  <ContextMenu.RadioGroup value={feature.value} onValueChange={(value) => feature.setValue(value)}>
    {#each feature.choices as choice (choice.value)}
      <ContextMenu.RadioItem value={choice.value} closeOnSelect={false}>{choice.label}</ContextMenu.RadioItem>
    {/each}
  </ContextMenu.RadioGroup>
{/snippet}

<ContextMenu.Root bind:open={menuOpen}>
  <ContextMenu.Trigger>
    {#snippet child({ props })}
      <div
        {...props}
        bind:this={host}
        bind:clientWidth={width}
        bind:clientHeight={height}
        class="relative size-full min-h-0 min-w-0 touch-none overflow-hidden bg-pane"
        onpointermove={(event) => (cursor = Geometry.unproject(eventPoint(event), view))}
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
            onpointerclick={(event) => {
              if (event.evt.button !== 0 || event.evt.altKey || selectionStart || menuOpen) return;
              const screen = eventPoint(event.evt);
              onclick?.(Geometry.unproject(screen, view), names(screen), screen);
            }}
            oncontextmenu={(event) => {
              menuPreview = null;
              const screen = eventPoint(event.evt);
              menuSelection = {
                point: Geometry.unproject(screen, view),
                names: names(screen),
                region: marquee ? { ...marquee } : null
              };
            }}
          >
            <Layer>
              <Group {...Geometry.world(view.scale)} listening={false}>
                <Rect
                  x={imaged.minX}
                  y={imaged.minY}
                  width={imaged.maxX - imaged.minX}
                  height={imaged.maxY - imaged.minY}
                  fill={hexWithAlpha(colors.fg, 0.025)}
                  stroke={colors.lineFaint}
                  strokeWidth={1}
                  strokeScaleEnabled={false}
                />
                <Rect
                  x={specimen.minX}
                  y={specimen.minY}
                  width={specimen.maxX - specimen.minX}
                  height={specimen.maxY - specimen.minY}
                  fill={hexWithAlpha(colors.fg, 0.025)}
                  stroke={colors.lineFaint}
                  strokeWidth={1}
                  strokeScaleEnabled={false}
                />
                <Rect
                  x={travel.minX}
                  y={travel.minY}
                  width={travel.maxX - travel.minX}
                  height={travel.maxY - travel.minY}
                  stroke={colors.lineMuted}
                  strokeWidth={1}
                  dash={[4, 4]}
                  strokeScaleEnabled={false}
                />
              </Group>
              {@render children?.()}
              {#if marquee}
                <Marquee bind:bounds={marquee} />
              {/if}
            </Layer>
          </Stage>
          {@render overlay?.(view, width, height, cursor, actions)}
        {/if}
      </div>
    {/snippet}
  </ContextMenu.Trigger>
  <ContextMenu.Content class="min-w-56">
    {#if menuSelection}
      {@render menu?.(menuSelection, targets, actions)}
    {/if}
    {#if layered.length}
      <ContextMenu.Separator />
      <ContextMenu.Sub>
        <ContextMenu.SubTrigger>Layers</ContextMenu.SubTrigger>
        <ContextMenu.SubContent class="min-w-44">
          {#each layered as feature (feature.id)}
            {#if 'choices' in feature}
              <ContextMenu.Separator />
              <ContextMenu.Group>
                <ContextMenu.GroupHeading class="text-fg-muted">{feature.label}</ContextMenu.GroupHeading>
                {@render choices(feature)}
              </ContextMenu.Group>
            {:else}
              <ContextMenu.CheckboxItem
                checked={feature.visible}
                closeOnSelect={false}
                onCheckedChange={(visible) => feature.setVisible(visible)}
              >
                {feature.label}
              </ContextMenu.CheckboxItem>
            {/if}
          {/each}
        </ContextMenu.SubContent>
      </ContextMenu.Sub>
    {/if}
    {#each own as feature (feature.id)}
      <ContextMenu.Sub>
        <ContextMenu.SubTrigger>{feature.label}</ContextMenu.SubTrigger>
        <ContextMenu.SubContent class="min-w-44">{@render choices(feature)}</ContextMenu.SubContent>
      </ContextMenu.Sub>
    {/each}
  </ContextMenu.Content>
</ContextMenu.Root>
