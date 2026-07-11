<script lang="ts">
  import { type Preview } from '$lib/model';
  import SpinBox from '$lib/prop/numeric/SpinBox.svelte';
  import { cn } from '$lib/utils';

  interface Props {
    previewer: Preview;
    class?: string;
  }

  let { previewer, class: className = '' }: Props = $props();
</script>

<div class={cn('flex items-center gap-1.5 font-mono text-xs', className)}>
  <SpinBox model={previewer.zoomModel} prefix="Zoom" decimals={2} numCharacters={6} align="right" steppers={false} />
  <SpinBox model={previewer.panXModel} prefix="X" decimals={2} numCharacters={5} align="right" steppers={false} />
  <SpinBox model={previewer.panYModel} prefix="Y" decimals={2} numCharacters={5} align="right" steppers={false} />
</div>
