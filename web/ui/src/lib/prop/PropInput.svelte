<script lang="ts">
  import { cn } from '$lib/utils';

  import * as Bool from './bool';
  import * as Enumerated from './enumerated';
  import { type AnyPropModel, BoolModel, EnumeratedModel, NumericModel, StringModel } from './models.svelte';
  import * as Numeric from './numeric';
  import * as Text from './text';

  interface Props {
    model: AnyPropModel | undefined;
    disabled?: boolean;
    size?: 'xs' | 'sm' | 'md' | 'lg';
    class?: string;
  }

  let { model, disabled = false, size = 'xs', class: className = '' }: Props = $props();

  function formatFallback(value: unknown): string {
    if (value === undefined || value === null) return '—';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }
</script>

{#if !model}
  <span class={cn('text-xs text-fg-faint', className)}>—</span>
{:else if model instanceof EnumeratedModel}
  <Enumerated.Select model={model as EnumeratedModel<string>} {disabled} {size} class={className} />
{:else if model instanceof BoolModel}
  <Bool.Toggle {model} {disabled} {size} class={className} />
{:else if model instanceof NumericModel}
  {#if model.min != null && model.max != null}
    <Numeric.SpinSlider {model} {disabled} class={className} />
  {:else}
    <Numeric.SpinBox {model} {disabled} class={className} />
  {/if}
{:else if model instanceof StringModel}
  <Text.Input {model} {disabled} {size} class={className} />
{:else}
  <span class={cn('font-mono text-xs text-fg-muted', className)}>{formatFallback(model.value)}</span>
{/if}
