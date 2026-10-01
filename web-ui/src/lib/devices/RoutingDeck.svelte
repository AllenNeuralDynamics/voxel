<script lang="ts">
  import { resolve } from '$app/paths';
  import { Button, Select } from '$lib/kit';
  import { EnumeratedModel, type Instrument, type RoutingDimension } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import { formatSpatialDistance } from '$lib/spatial-units';
  import { cn, displayName, toastError } from '$lib/utils';

  import DeckHeader from './DeckHeader.svelte';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  let { instrument, class: className }: Props = $props();

  // Requests track loading; the dropdown value comes from observed hardware state.
  let pending = $state<Record<string, string>>({});
  let applying = $state(false);

  const dimensions = $derived([...instrument.routingDimensions.values()]);
  const disabled = $derived(
    instrument.mode === 'capture' ||
      instrument.edits.busy ||
      applying ||
      Object.keys(pending).length > 0 ||
      dimensions.some((d) => d.moving)
  );
  const canApply = $derived(
    !disabled && dimensions.some((dimension) => dimension.resolved != null && dimension.current !== dimension.resolved)
  );

  function ruleSummary({ model, axis }: RoutingDimension): string {
    if (model instanceof EnumeratedModel) return `Selected: ${displayName(model.value)}`;
    return `${axis?.toUpperCase()}: Lower < ${formatSpatialDistance(model.value, prefs.spatialUnit.get())} ≤ Upper`;
  }

  function select(dimension: string, route: string): void {
    if (disabled) return;
    pending[dimension] = route;
    toastError(
      instrument.selectRoute(dimension, route).finally(() => {
        delete pending[dimension];
      })
    );
  }

  function applyRules(): void {
    if (!canApply) return;
    applying = true;
    toastError(
      instrument.applyRoutingRule().finally(() => {
        applying = false;
      })
    );
  }
</script>

<div class={cn('flex w-full min-w-68 flex-col', className)}>
  <DeckHeader title="Routing" count={dimensions.length}>
    {#snippet actions()}
      <Button
        variant="ghost"
        size="xs"
        class="text-sm font-normal"
        disabled={!canApply}
        loading={applying}
        title="Apply routing rules at the current stage position"
        onclick={applyRules}
      >
        Apply rules
      </Button>
    {/snippet}
  </DeckHeader>
  <div class="px-3 pt-1 pb-3">
    {#each dimensions as dimension (dimension.id)}
      {@const options = dimension.routes.map((route) => ({ value: route, label: dimension.routeLabel(route) }))}
      <div class="flex items-center gap-2 py-1.5">
        <a
          href={resolve(
            `/stations/[stationId]/instruments/[instrumentId]/routing#${encodeURIComponent(`routing-${dimension.id}`)}`,
            { stationId: instrument.stationId, instrumentId: instrument.id }
          )}
          class="flex min-w-0 flex-1 items-center gap-1 rounded-sm text-base font-medium text-fg hover:text-fg-accent focus-visible:outline-2 focus-visible:outline-border-focused"
          title={`Edit routing rule · ${ruleSummary(dimension)}`}
        >
          <span class="truncate">{displayName(dimension.id)}</span>
        </a>
        <Select
          variant="ghost"
          size="xs"
          side="top"
          class="ml-auto w-42 tabular-nums"
          value={dimension.current ?? ''}
          {options}
          {disabled}
          placeholder={dimension.moving ? 'Switching…' : 'Unknown'}
          loading={dimension.moving || pending[dimension.id] != null || applying}
          onchange={(route) => select(dimension.id, route)}
        >
          {#snippet trailing(option)}
            {#if option.value === dimension.resolved}
              <span
                class="inline-block size-2 shrink-0 rounded-full bg-primary align-middle"
                role="img"
                aria-label="Selected by rule"
                title="Selected by rule"
              ></span>
            {/if}
          {/snippet}
        </Select>
      </div>
    {/each}
  </div>
</div>
