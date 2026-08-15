<script lang="ts">
  import { watch } from 'runed';

  import { Button, Select } from '$lib/kit';
  import { type Instrument, type OpticalRoutingPolicy } from '$lib/model';
  import { cn, displayName, toastError, trimFloat } from '$lib/utils';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  interface RoutingDimension {
    id: string;
    routes: string[];
    current?: string;
    target?: string;
    moving: boolean;
    policy?: OpticalRoutingPolicy;
  }

  let { instrument, class: className }: Props = $props();

  // Keep a user-selected destination stable while its selectors move through intermediate positions.
  let optimistic = $state<Record<string, string>>({});

  const dimensions = $derived.by<RoutingDimension[]>(() =>
    Object.entries(instrument.hal.optical_routing).map(([id, routes]) => {
      const selectors = new Set(Object.values(routes).flatMap((positions) => Object.keys(positions)));
      const moving = [...selectors].some((selector) => instrument.discreteAxes.get(selector)?.isMoving?.value === true);
      const current = Object.entries(routes).find(([, positions]) =>
        Object.entries(positions).every(
          ([selector, position]) => instrument.discreteAxes.get(selector)?.label === position
        )
      )?.[0];
      return {
        id,
        routes: Object.keys(routes),
        current,
        target: instrument.routingTargets[id],
        moving,
        policy: instrument.state.routing[id]
      };
    })
  );

  const displayedRoute = (dimension: RoutingDimension): string | undefined =>
    optimistic[dimension.id] ?? (dimension.moving ? dimension.target : dimension.current);

  function policySummary(policy: OpticalRoutingPolicy): string {
    if (policy.type === 'fixed') return `Fixed to ${displayName(policy.route)}`;
    return `${policy.axis.toUpperCase()} split at ${trimFloat(policy.threshold / 1000, 4)} mm · ${displayName(
      policy.lower
    )} → ${displayName(policy.upper)}`;
  }

  const canRevert = $derived(
    dimensions.some((dimension) => dimension.target != null && displayedRoute(dimension) !== dimension.target)
  );

  function override(dimension: string, route: string): void {
    optimistic[dimension] = route;
    const request = instrument.overrideOpticalRoute(dimension, route);
    request.catch(() => delete optimistic[dimension]);
    toastError(request);
  }

  function revert(): void {
    for (const dimension of dimensions) {
      if (dimension.target != null) optimistic[dimension.id] = dimension.target;
    }
    const request = instrument.applyOpticalRouting();
    request.catch(() => {
      optimistic = {};
    });
    toastError(request);
  }

  // Once hardware reaches the optimistic destination—or finishes without reaching it—return to live state.
  const wasMoving: Record<string, boolean> = {};
  watch(
    () => dimensions.map(({ id, current, moving }) => `${id}:${current ?? ''}:${moving ? 1 : 0}`).join(','),
    () => {
      for (const dimension of dimensions) {
        if (
          optimistic[dimension.id] != null &&
          (dimension.current === optimistic[dimension.id] || (wasMoving[dimension.id] && !dimension.moving))
        ) {
          delete optimistic[dimension.id];
        }
        wasMoving[dimension.id] = dimension.moving;
      }
    }
  );
</script>

<div class={cn('flex w-full min-w-68 flex-col py-2', className)}>
  <div class="flex shrink-0 items-center gap-2 px-3 py-1">
    <span class="font-medium tracking-wide text-fg-muted uppercase">Routing</span>
    <div class="flex-1"></div>
    <Button
      variant="ghost"
      size="xs"
      disabled={!canRevert}
      class={cn(canRevert ? 'text-danger' : 'opacity-50')}
      onclick={revert}
    >
      Revert
    </Button>
    <span class="font-mono text-[10px] text-fg-faint tabular-nums">{dimensions.length}</span>
  </div>

  <div class="flex flex-col gap-2 px-3 py-2">
    {#each dimensions as dimension (dimension.id)}
      {@const options = dimension.routes.map((route) => ({ value: route, label: displayName(route) }))}
      <div class="flex flex-col gap-1 rounded-xs border border-border bg-card px-2.5 py-1.5">
        <div class="flex items-center gap-2">
          <span class="min-w-0 flex-1 truncate text-base font-medium text-fg">
            {displayName(dimension.id)}
          </span>
          <Select
            variant="ghost"
            size="xs"
            side="top"
            class="ml-auto w-42 tabular-nums"
            value={displayedRoute(dimension) ?? ''}
            {options}
            placeholder="Mixed"
            loading={dimension.moving}
            onchange={(route) => override(dimension.id, route)}
          >
            {#snippet trailing(option)}
              {#if option.value === dimension.target}
                <span
                  class="inline-block size-1.5 shrink-0 rounded-full bg-fg-muted align-middle"
                  title="Routing target"
                ></span>
              {/if}
            {/snippet}
          </Select>
        </div>
        {#if dimension.policy}
          <div class="truncate text-sm text-fg-muted" title={policySummary(dimension.policy)}>
            <span class="mr-1.5 text-fg-faint">Policy</span>
            {policySummary(dimension.policy)}
          </div>
        {/if}
      </div>
    {/each}
  </div>
</div>
