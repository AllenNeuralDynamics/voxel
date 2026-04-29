<script lang="ts">
  import { Select } from 'bits-ui';

  import { ChevronUpDown } from '$lib/icons';
  import { selectVariants } from '$lib/kit/Select.svelte';
  import { cn, sanitizeString } from '$lib/utils';

  import type { StacksManager } from './stacks.svelte';
  import StackStatusIcon from './StackStatusIcon.svelte';

  interface Props {
    stacks: StacksManager;
    size?: 'xs' | 'sm' | 'md' | 'lg';
    class?: string;
  }

  let { stacks, size = 'sm', class: className }: Props = $props();

  const list = $derived(stacks.list);
  const value = $derived(stacks.selected[0]?.stack_id ?? list[0]?.stack_id ?? '');

  const stackItems = $derived(
    list.map((s, i) => ({
      value: s.stack_id,
      label: `#${i + 1} ${sanitizeString(s.profile_id)}`
    }))
  );

  const selectedStack = $derived(list.find((s) => s.stack_id === value));
  const selectedIndex = $derived(list.findIndex((s) => s.stack_id === value) + 1);
  const styles = $derived(selectVariants({ variant: 'filled', size }));
  const iconSize = $derived({ xs: 10, sm: 12, md: 14, lg: 16 }[size]);

  function handleChange(stackId: string | undefined) {
    if (!stackId) return;
    const stack = list.find((s) => s.stack_id === stackId);
    if (stack) stacks.select([stack]);
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
      {#if list.length === 0}
        <div class="px-3 py-2 text-xs text-fg-muted">No stacks configured</div>
      {:else}
        <Select.Viewport class="max-h-(--bits-select-content-available-height) overflow-y-auto">
          <Select.Group>
            {#each list as stack, i (stack.stack_id)}
              <Select.Item
                value={stack.stack_id}
                label="#{i + 1} {sanitizeString(stack.profile_id)}"
                class={cn(styles.item(), 'items-center gap-2', value === stack.stack_id && 'bg-element-selected/50')}
              >
                <div class="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-0.5">
                  <span class="text-fg">#{i + 1} {sanitizeString(stack.profile_id)}</span>
                  <span class="text-xs text-fg-muted tabular-nums">
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
