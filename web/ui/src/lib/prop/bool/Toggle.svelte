<script lang="ts">
  import { Switch as KitSwitch, type SwitchVariants } from '$lib/kit';
  import type { BoolModel } from '$lib/model';

  interface Props extends SwitchVariants {
    model: BoolModel;
    disabled?: boolean;
    style?: string;
    class?: string;
  }

  let { model, disabled, size, style, class: className = '' }: Props = $props();
</script>

<KitSwitch
  checked={model.value === true}
  onCheckedChange={(checked) => model.patch(checked)}
  {disabled}
  {size}
  {style}
  class={className}
/>
