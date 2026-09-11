<script lang="ts">
  import { onDestroy } from 'svelte';

  import { Button, Select } from '$lib/kit';
  import {
    type EditContext,
    getVoxelStation,
    type Instrument,
    type RoutingDimension,
    type RoutingRule,
    type SplitRoutingRule
  } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import { SpinBox } from '$lib/prop/numeric';
  import { useNumericModel } from '$lib/prop/numeric/model.svelte';
  import { getSpatialUnit } from '$lib/spatial-units';
  import { cn, displayName, toastError } from '$lib/utils';

  import { asFixedRule, asSplitRule } from './rule';

  interface Props {
    instrument: Instrument;
    dimension: RoutingDimension;
  }

  let { instrument, dimension }: Props = $props();

  const app = getVoxelStation();
  const unit = $derived(getSpatialUnit(prefs.spatialUnit.get()));
  let pendingRule = $state<RoutingRule | null>(null);
  const rule = $derived(pendingRule ?? dimension.rule);
  let writes = $state(0);
  const saving = $derived(writes > 0);
  let applying = $state(false);
  let inputRevision = $state(0);
  let saveRevision = 0;
  let echoed = false;

  // Reconcile the optimistic value without making request ordering wait for the feed.
  const stopWatching = app.client.onView((view) => {
    if (
      pendingRule &&
      view.session?.info.id === instrument.sessionId &&
      JSON.stringify(view.session.instrument.routing[dimension.id]) === JSON.stringify(pendingRule)
    ) {
      echoed = true;
      if (!writes) pendingRule = null;
    }
  });
  onDestroy(() => {
    threshold.endEdit();
    stopWatching();
  });

  const routes = $derived(dimension.ruleRoutes);
  const routeOptions = $derived(routes.map((route) => ({ value: route, label: displayName(route) })));
  const canSplit = $derived(routes.length >= 2);
  const disabled = $derived(instrument.mode === 'capture' || applying);
  const threshold = useNumericModel(() => ({
    value: rule.type === 'split' ? rule.threshold / unit.scale : 0,
    step: 1 / unit.scale,
    throttleMs: 100,
    onEditStart: () => instrument.edits.hold(),
    disabled,
    onChange: (value, context) => updateSplit({ threshold: value * unit.scale }, context)
  }));

  function save(next: RoutingRule, context: EditContext = {}): void {
    if (disabled || JSON.stringify(next) === JSON.stringify(rule)) return;
    const revision = ++saveRevision;
    pendingRule = next;
    echoed = false;
    writes += 1;
    toastError(
      instrument
        .setRoutingRule(dimension.id, next, context)
        .catch((error) => {
          if (revision !== saveRevision) return;
          pendingRule = null;
          threshold.dispose();
          threshold.update({
            kind: 'float',
            value: dimension.rule.type === 'split' ? dimension.rule.threshold / unit.scale : 0
          });
          inputRevision += 1;
          throw error;
        })
        .finally(() => {
          writes -= 1;
          if (!writes && (echoed || JSON.stringify(pendingRule) === JSON.stringify(dimension.rule))) pendingRule = null;
        })
    );
  }

  function selectType(type: RoutingRule['type']): void {
    if (type === rule.type) return;
    save(
      type === 'fixed'
        ? asFixedRule(rule, routes, dimension.resolved)
        : asSplitRule(rule, routes, instrument.stage.position('x'))
    );
  }

  function updateSplit(changes: Partial<Omit<SplitRoutingRule, 'type'>>, context: EditContext = {}): void {
    if (rule.type === 'split') save({ ...rule, ...changes }, context);
  }

  function apply(): void {
    if (disabled || saving || dimension.moving || dimension.resolved == null) return;
    applying = true;
    toastError(
      instrument.applyRoutingRule(dimension.id).finally(() => {
        applying = false;
      })
    );
  }

  function useCurrentPosition(): void {
    if (rule.type === 'split') updateSplit({ threshold: instrument.stage.position(rule.axis) });
  }

  function swapRoutes(): void {
    if (rule.type === 'split') updateSplit({ lower: rule.upper, upper: rule.lower });
  }

  function routeOptionsExcept(route: string): { value: string; label: string }[] {
    return routeOptions.filter((option) => option.value !== route);
  }
</script>

<div class="min-w-0">
  <div class="flex min-h-ui-xs flex-wrap items-center gap-2">
    <h2 class="min-w-0 text-base text-fg">{displayName(dimension.id)}</h2>
    <span class="ml-auto text-sm text-fg-muted" role="status">{saving ? 'Saving…' : ''}</span>
  </div>
  {#key inputRevision}
    <div class="grid grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)_auto] content-start items-center gap-x-2 gap-y-3 py-3">
      <div class="self-center text-base text-fg-muted">Rule</div>
      <div class="col-span-3">
        <div class="grid h-ui-sm w-full grid-cols-2 items-center rounded border border-input bg-canvas/50 p-0.5">
          <button
            type="button"
            {disabled}
            class={cn(
              'h-full w-full rounded-sm px-3 text-base transition-colors',
              rule.type === 'fixed' ? 'bg-element-selected text-fg shadow-sm' : 'text-fg-muted hover:text-fg'
            )}
            onclick={() => selectType('fixed')}
          >
            Fixed
          </button>
          <button
            type="button"
            disabled={disabled || !canSplit}
            title={canSplit ? undefined : 'A split rule requires at least two supported routes'}
            class={cn(
              'h-full w-full rounded-sm px-3 text-base transition-colors disabled:cursor-not-allowed disabled:opacity-40',
              rule.type === 'split' ? 'bg-element-selected text-fg shadow-sm' : 'text-fg-muted hover:text-fg'
            )}
            onclick={() => selectType('split')}
          >
            Stage split
          </button>
        </div>
      </div>

      {#if rule.type === 'fixed'}
        <div class="self-center text-base text-fg-muted">Route</div>
        <div class="col-span-3">
          <Select
            value={rule.route}
            options={routeOptions}
            size="sm"
            class="w-full"
            {disabled}
            onchange={(route) => save({ type: 'fixed', route })}
          />
        </div>
      {:else}
        <div class="self-center text-base text-fg-muted">Axis</div>
        <div class="col-span-3">
          <div class="grid h-ui-sm w-full grid-cols-2 items-center rounded border border-input bg-canvas/50 p-0.5">
            {#each ['x', 'y'] as axis (axis)}
              <button
                type="button"
                {disabled}
                class={cn(
                  'h-full w-full rounded-sm px-3 text-base uppercase transition-colors',
                  rule.axis === axis ? 'bg-element-selected text-fg shadow-sm' : 'text-fg-muted hover:text-fg'
                )}
                onclick={() => updateSplit({ axis: axis as 'x' | 'y' })}
              >
                {axis}
              </button>
            {/each}
          </div>
        </div>

        <div class="self-center text-base text-fg-muted" title="Drag to adjust threshold" {@attach threshold.scrubber}>
          Threshold
        </div>
        {#key unit.value}
          <SpinBox
            model={threshold}
            decimals={unit.decimals}
            numCharacters={9}
            suffix={unit.label}
            size="sm"
            class="col-span-2 w-full"
            {disabled}
          />
        {/key}
        <Button variant="secondary" size="xs" {disabled} onclick={useCurrentPosition}>
          Use current {rule.axis.toUpperCase()}
        </Button>

        <div class="self-center text-base text-fg-muted">Routes</div>
        <Select
          value={rule.lower}
          options={routeOptionsExcept(rule.upper)}
          prefix="<"
          size="sm"
          class="min-w-0"
          {disabled}
          onchange={(lower) => updateSplit({ lower })}
        />
        <Select
          value={rule.upper}
          options={routeOptionsExcept(rule.lower)}
          prefix="≥"
          size="sm"
          class="min-w-0"
          {disabled}
          onchange={(upper) => updateSplit({ upper })}
        />
        <Button variant="secondary" size="xs" {disabled} onclick={swapRoutes}>Swap</Button>
      {/if}
    </div>
  {/key}

  <div class="flex flex-wrap items-center gap-2 text-sm text-fg-muted">
    <span>
      {#if dimension.moving || applying}
        Switching…
      {:else}
        Current: {dimension.current != null ? displayName(dimension.current) : 'Unknown'}
        · Rule: {dimension.resolved != null ? displayName(dimension.resolved) : 'Unknown'}
        {#if dimension.current != null && dimension.current === dimension.resolved}
          · Matches rule
        {/if}
      {/if}
    </span>
    <Button
      variant="ghost"
      size="xs"
      class="ml-auto"
      loading={applying}
      disabled={disabled ||
        saving ||
        dimension.moving ||
        dimension.resolved == null ||
        dimension.current === dimension.resolved}
      title="Move hardware to the route selected by this rule"
      onclick={apply}
    >
      Apply to hardware
    </Button>
  </div>

  {#if instrument.mode === 'capture'}
    <p class="text-base text-fg-muted">Routing rules cannot be changed during capture.</p>
  {/if}
</div>
