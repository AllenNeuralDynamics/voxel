<script lang="ts" generics="T extends string | number">
  import { cn } from '../../utils/cn';
  import type { EnumeratedProps } from './enumerated.svelte';
  import RadioBar from './RadioBar.svelte';
  import Select from './Select.svelte';

  /**
   * Picks 1 option: a RadioBar while all its options fit in the box, else a Select. A hidden copy of the RadioBar
   * gives the width it needs, so the switch follows the options as well as the box.
   */
  type Props = EnumeratedProps<T> & {
    /** The text of an option. By default, the option shows as it is. */
    formatLabel?: (option: T) => string;
    disabled?: boolean;
    /** The option it should be at. While the value is another, that value shows in the warning color and this option
     * in the accent color. */
    expected?: T | null;
    size?: 'sm' | 'md' | 'lg';
    'aria-label'?: string;
    class?: string;
  };

  let {
    formatLabel = String,
    disabled = false,
    expected = null,
    size = 'sm',
    class: className,
    ...rest
  }: Props = $props();
  const away = $derived(expected != null && rest.value != null && rest.value !== expected);

  let room = $state(0);
  let needed = $state(0);
  const fits = $derived(needed > 0 && needed <= room);
</script>

{#snippet mark(option: T)}
  {#if away && option === expected}<span class="sr-only">expected</span>{/if}
{/snippet}

<div class={cn('relative min-w-0', className)} bind:clientWidth={room}>
  <!-- The copy is placed in this box, so it never widens the page. -->
  <div class="pointer-events-none invisible absolute top-0 left-0 w-max" aria-hidden="true" inert>
    <div bind:offsetWidth={needed}>
      <RadioBar {...rest as EnumeratedProps<T>} display={formatLabel} {disabled} {size} trailing={mark} />
    </div>
  </div>
  {#if fits}
    <RadioBar
      {...rest as EnumeratedProps<T>}
      display={formatLabel}
      {disabled}
      {size}
      trailing={mark}
      accented={away ? expected : null}
      class={cn('w-full', away && '[&_[data-state=checked]]:text-warning-fg')}
    />
  {:else}
    <Select
      {...rest as EnumeratedProps<T>}
      {formatLabel}
      {disabled}
      {size}
      trailing={mark}
      accented={away ? expected : null}
      class={cn(away && 'text-warning-fg')}
    />
  {/if}
</div>
