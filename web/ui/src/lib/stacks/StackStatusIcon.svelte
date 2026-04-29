<script lang="ts">
  import type { StackStatus } from '$lib/config';
  import { AlertCircleOutline, Check, DotsSpinner, LucideCircle, Minus } from '$lib/icons';

  interface Props {
    status: StackStatus;
    size?: number;
    class?: string;
  }

  let { status, size = 12, class: className = '' }: Props = $props();
</script>

<span data-stack-status={status} class="inline-flex text-(--stack-status) {className}">
  {#if status === 'acquiring'}
    <DotsSpinner width={size} height={size} />
  {:else if status === 'completed'}
    <Check width={size} height={size} />
  {:else if status === 'failed'}
    <AlertCircleOutline width={size} height={size} />
  {:else if status === 'skipped'}
    <Minus width={size} height={size} />
  {:else}
    <LucideCircle width={size} height={size} />
  {/if}
</span>
