<script lang="ts">
  import { onMount, type Snippet, untrack } from 'svelte';
  import { Group, Image as KonvaImage, Rect } from 'svelte-konva';

  import { Crosshair } from '$lib/icons';
  import { ContextMenu } from '$lib/kit';

  import { getStageContext, type MenuSelection } from './context.svelte';
  import { type Bounds, intersect, worldTransform } from './geometry';

  let {
    id,
    label,
    bounds,
    image,
    revision = 0,
    color = '#38bdf8',
    visible = $bindable(true),
    selected = $bindable(false),
    menu,
    regionMenu,
    onselect,
    onactivate
  }: {
    id: string;
    label: string;
    bounds: Bounds;
    image?: HTMLImageElement | HTMLCanvasElement | ImageBitmap;
    revision?: number;
    color?: string;
    visible?: boolean;
    selected?: boolean;
    menu?: Snippet<[MenuSelection]>;
    regionMenu?: Snippet<[Bounds]>;
    onselect?: (selected: boolean) => void;
    onactivate?: () => void;
  } = $props();

  const context = getStageContext();
  let group = $state<Group>();
  let footprint = $state<Rect>();
  let previousRegion: Bounds | null | undefined;

  function select(next: boolean) {
    if (selected === next) return;
    selected = next;
    onselect?.(next);
  }

  $effect(() => {
    void revision;
    group?.node.getLayer()?.batchDraw();
  });

  $effect(() => {
    const region = context.marquee;
    if (context.selecting) return;
    const shown = visible;
    if (region || previousRegion !== undefined) {
      untrack(() => select(shown && !!region && !!intersect(bounds, region)));
    }
    previousRegion = region;
  });

  onMount(() =>
    context.register({
      id,
      get label() {
        return label;
      },
      get visible() {
        return visible;
      },
      setVisible: (next) => {
        visible = next;
      },
      menu(selection) {
        if ('bounds' in selection) {
          return intersect(bounds, selection.bounds) && (menu || regionMenu) ? imageMenu : undefined;
        }
        return footprint && selection.hits.includes(footprint.node) ? imageMenu : undefined;
      }
    })
  );
</script>

{#snippet imageMenu(selection: MenuSelection)}
  {#if 'point' in selection}
    <ContextMenu.Item onSelect={() => select(true)}>
      <Crosshair width="14" height="14" />
      Select
    </ContextMenu.Item>
  {/if}
  {@render menu?.(selection)}
  {#if 'bounds' in selection}
    {@render regionMenu?.(selection.bounds)}
  {/if}
{/snippet}

<Group bind:this={group} {visible} {...worldTransform(context.view.scale, context.orientation)}>
  {#if image}
    <KonvaImage
      {image}
      x={context.orientation.x > 0 ? bounds.minX : bounds.maxX}
      y={context.orientation.y > 0 ? bounds.maxY : bounds.minY}
      scaleX={context.orientation.x}
      scaleY={-context.orientation.y}
      width={bounds.maxX - bounds.minX}
      height={bounds.maxY - bounds.minY}
      listening={false}
    />
  {/if}
  <Rect
    bind:this={footprint}
    x={bounds.minX}
    y={bounds.minY}
    width={bounds.maxX - bounds.minX}
    height={bounds.maxY - bounds.minY}
    fill="transparent"
    stroke={color}
    strokeWidth={selected ? 2 : 1}
    strokeScaleEnabled={false}
    onpointerclick={(event) => {
      if (!event.evt.altKey && !context.marquee) select(true);
    }}
    onpointerdblclick={() => onactivate?.()}
  />
</Group>
