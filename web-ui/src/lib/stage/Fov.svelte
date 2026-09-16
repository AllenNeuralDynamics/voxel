<script lang="ts">
  import { onMount } from 'svelte';
  import { Group, Rect } from 'svelte-konva';

  import type { PreviewSession } from '$lib/preview/session.svelte';

  import { getStageContext } from './context.svelte';
  import FovImage from './FovImage.svelte';
  import { type Bounds, type Point, worldTransform } from './geometry';

  let {
    preview,
    bounds,
    visible = $bindable(true),
    onactivate
  }: {
    preview: PreviewSession | null;
    bounds: Bounds | null;
    visible?: boolean;
    onactivate?: () => void;
  } = $props();

  const context = getStageContext();
  const images = $derived(
    (preview?.channels ?? []).flatMap((channel) => {
      const frame = channel.overviewFrame;
      if (!channel.visible || !frame?.position_um || !frame.fov) return [];
      const { x, y } = frame.position_um;
      const [width, height] = frame.fov;
      if (!(width > 0 && height > 0)) return [];
      return [{ channel, rect: { x: x - width / 2, y: y - height / 2, width, height } }];
    })
  );

  /** Activate the FOV beneath another layer's hit target. */
  export function activateAt(point: Point) {
    if (!visible) return;
    const inBounds =
      bounds && point.x >= bounds.minX && point.x <= bounds.maxX && point.y >= bounds.minY && point.y <= bounds.maxY;
    const inImage = images.some(
      ({ rect }) =>
        point.x >= rect.x && point.x <= rect.x + rect.width && point.y >= rect.y && point.y <= rect.y + rect.height
    );
    if (inBounds || inImage) onactivate?.();
  }

  onMount(() =>
    context.register({
      id: 'live',
      label: 'Live FOV',
      get visible() {
        return visible;
      },
      setVisible: (next) => {
        visible = next;
      }
    })
  );
</script>

<Group {visible} {...worldTransform(context.view.scale, context.orientation)}>
  {#if visible && preview}
    <Group listening={false}>
      {#each images as image (image.channel)}
        <Rect {...image.rect} fill="black" />
      {/each}
    </Group>
    <Group>
      {#each images as image (image.channel)}
        <FovImage {preview} channel={image.channel} rect={image.rect} {onactivate} />
      {/each}
    </Group>
  {/if}
  {#if bounds && onactivate}
    <Rect
      x={bounds.minX}
      y={bounds.minY}
      width={bounds.maxX - bounds.minX}
      height={bounds.maxY - bounds.minY}
      fill="transparent"
      onpointerdblclick={() => onactivate?.()}
    />
  {/if}
</Group>
