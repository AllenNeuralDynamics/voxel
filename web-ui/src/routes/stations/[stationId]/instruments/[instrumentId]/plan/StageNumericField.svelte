<script lang="ts">
  import type { ComponentProps } from 'svelte';

  import { Crosshair } from '$lib/icons';
  import { Button } from '$lib/kit';
  import type { Stage } from '$lib/model';
  import { NumericField } from '$lib/prop/numeric';

  type Props = Omit<ComponentProps<typeof NumericField>, 'controls'> & {
    stage?: Stage | null;
    axis: 'x' | 'y' | 'z';
  };

  let {
    stage,
    axis,
    value = $bindable(null),
    disabled = false,
    oneditstart,
    oncommit,
    ...fieldProps
  }: Props = $props();

  const position = $derived(stage?.axis(axis).position?.value ?? null);

  function useStagePosition() {
    if (disabled || position == null || Object.is(value, position)) return;
    const release = oneditstart?.();
    value = position;
    oncommit?.(position);
    if (typeof release === 'function') release();
  }
</script>

<NumericField bind:value {disabled} {oneditstart} {oncommit} {...fieldProps}>
  {#snippet controls()}
    <Button
      variant="ghost"
      size="icon-xs"
      class="h-full rounded-none border-0 text-fg-muted focus-visible:ring-offset-0 focus-visible:ring-inset"
      disabled={disabled || position == null}
      aria-label="Use current stage position"
      title="Use current stage position"
      onclick={useStagePosition}
    >
      <Crosshair class="size-3.5" />
    </Button>
  {/snippet}
</NumericField>
