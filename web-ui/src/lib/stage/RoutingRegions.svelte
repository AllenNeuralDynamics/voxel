<script lang="ts">
  import { onMount } from 'svelte';
  import { Group, Rect } from 'svelte-konva';

  import { getStageContext } from './context.svelte';
  import { type Bounds, screenRect, screenTransform } from './geometry';

  let {
    regions,
    visible = $bindable(true)
  }: {
    regions: { bounds: Bounds; color: string }[];
    visible?: boolean;
  } = $props();

  const context = getStageContext();
  onMount(() =>
    context.register({
      id: 'routing-regions',
      label: 'Routing regions',
      menuOrder: 1,
      get visible() {
        return visible;
      },
      setVisible: (next) => {
        visible = next;
      }
    })
  );
</script>

<Group {visible} listening={false} opacity={0.03} {...screenTransform(context.view)}>
  {#each regions as region, index (index)}
    <Rect {...screenRect(region.bounds, context.view, context.orientation)} fill={region.color} />
  {/each}
</Group>
