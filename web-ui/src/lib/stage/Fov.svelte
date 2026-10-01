<script lang="ts">
  import { onMount } from 'svelte';
  import { Group, Rect } from 'svelte-konva';

  import type { PreviewSession } from '$lib/preview/session.svelte';

  import { getStageContext } from './context.svelte';
  import FovImage from './FovImage.svelte';
  import { worldTransform } from './geometry';

  let {
    preview,
    visible = $bindable(true)
  }: {
    preview: PreviewSession | null;
    visible?: boolean;
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

  onMount(() =>
    context.register({
      id: 'live',
      label: 'Live FOV',
      menuOrder: 0,
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
        <FovImage {preview} channel={image.channel} rect={image.rect} />
      {/each}
    </Group>
  {/if}
</Group>
