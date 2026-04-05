<script lang="ts">
  import type { Session } from '$lib/main';
  import { sanitizeString, cn } from '$lib/utils';
  import { selectVariants } from '$lib/ui/kit/Select.svelte';
  import { ChevronUpDown } from '$lib/icons';
  import StackStatusIcon from '$lib/ui/StackStatusIcon.svelte';
  import { Select } from 'bits-ui';

  interface Props {
    session: Session;
    size?: 'xs' | 'sm' | 'md' | 'lg';
    class?: string;
  }

  let { session, size = 'sm', class: className }: Props = $props();

  // Value tracks session selection reactively
  const value = $derived(session.selectedStacks[0]?.stack_id ?? session.stacks[0]?.stack_id ?? '');

  const stackItems = $derived(
    session.stacks.map((s, i) => ({
      value: s.stack_id,
      label: `#${i + 1} ${sanitizeString(s.profile_id)}`
    }))
  );

  const selectedStack = $derived(session.stacks.find((s) => s.stack_id === value));
  const selectedIndex = $derived(session.stacks.findIndex((s) => s.stack_id === value) + 1);
  const styles = $derived(selectVariants({ variant: 'filled', size }));
  const iconSize = $derived({ xs: 10, sm: 12, md: 14, lg: 16 }[size]);

  function handleChange(stackId: string | undefined) {
    if (!stackId) return;
    const stack = session.stacks.find((s) => s.stack_id === stackId);
    if (stack) session.selectStacks([stack]);
  }
</script>

<Select.Root type="single" {value} onValueChange={handleChange} items={stackItems}>
  <div class="relative">
    <Select.Trigger class={cn(styles.trigger(), 'rounded-md px-3 pr-8', className)}>
      <span class="truncate">
        {#if selectedStack}
          #{selectedIndex} {sanitizeString(selectedStack.profile_id)}
        {:else}
          <span class="text-fg-muted">No stacks</span>
        {/if}
      </span>
    </Select.Trigger>
    <div class="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2">
      <ChevronUpDown class="opacity-50" width={iconSize} height={iconSize} />
    </div>
  </div>

  <Select.Portal>
    <Select.Content align="start" class={styles.content()}>
      {#if session.stacks.length === 0}
        <div class="px-3 py-2 text-xs text-fg-muted">No stacks configured</div>
      {:else}
        <Select.Viewport class="max-h-(--bits-select-content-available-height) overflow-y-auto">
          <Select.Group>
            {#each session.stacks as stack, i (stack.stack_id)}
              <Select.Item
                value={stack.stack_id}
                label="#{i + 1} {sanitizeString(stack.profile_id)}"
                class={cn(
                  styles.item(),
                  'items-center gap-2',
                  value === stack.stack_id && 'bg-element-selected/50'
                )}
              >
                  <div class="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-0.5">
                  <span class="text-fg">#{i + 1} {sanitizeString(stack.profile_id)}</span>
                  <span class="text-xs tabular-nums text-fg-muted">
                    X {(stack.x / 1000).toFixed(2)} Y {(stack.y / 1000).toFixed(2)} mm
                  </span>
                </div>
                <StackStatusIcon status={stack.status} size={12} />
              </Select.Item>
            {/each}
          </Select.Group>
        </Select.Viewport>
      {/if}
    </Select.Content>
  </Select.Portal>
</Select.Root>
