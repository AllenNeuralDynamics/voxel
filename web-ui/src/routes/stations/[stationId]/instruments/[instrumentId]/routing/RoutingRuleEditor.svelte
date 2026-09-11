<script lang="ts">
  import { watch } from 'runed';

  import { Button, Select } from '$lib/kit';
  import type { Instrument, RoutingDimension, RoutingRule, SplitRoutingRule } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import { SpinBox } from '$lib/prop/numeric';
  import { getSpatialUnit } from '$lib/spatial-units';
  import { cn, displayName, toastError } from '$lib/utils';

  import { asFixedRule, asSplitRule, cloneRule } from './rule';

  interface Props {
    instrument: Instrument;
    dimension: RoutingDimension;
  }

  let { instrument, dimension }: Props = $props();

  const unit = $derived(getSpatialUnit(prefs.spatialUnit.get()));
  let draft = $state<RoutingRule>({ type: 'fixed', route: '' });
  let sourceKey = $state('');
  let saving = $state(false);
  let applying = $state(false);

  const routes = $derived(dimension.ruleRoutes);
  const routeOptions = $derived(routes.map((route) => ({ value: route, label: displayName(route) })));
  const canSplit = $derived(routes.length >= 2);
  const changed = $derived(JSON.stringify(draft) !== JSON.stringify(dimension.rule));
  const disabled = $derived(instrument.mode === 'capture' || saving || applying);

  watch(
    () => `${dimension.id}:${JSON.stringify(dimension.rule)}`,
    (key) => {
      if (key !== sourceKey) {
        sourceKey = key;
        draft = cloneRule(dimension.rule);
      }
    }
  );

  function selectType(type: RoutingRule['type']): void {
    if (type === draft.type) return;
    draft =
      type === 'fixed'
        ? asFixedRule(draft, routes, dimension.resolved)
        : asSplitRule(draft, routes, instrument.stage.position('x'));
  }

  function updateSplit(changes: Partial<Omit<SplitRoutingRule, 'type'>>): void {
    if (draft.type === 'split') draft = { ...draft, ...changes };
  }

  function reset(): void {
    draft = cloneRule(dimension.rule);
  }

  function save(): void {
    if (!changed || disabled) return;
    saving = true;
    toastError(
      instrument.setRoutingRule(dimension.id, draft).finally(() => {
        saving = false;
      })
    );
  }

  function apply(): void {
    if (disabled || changed || dimension.moving || dimension.resolved == null) return;
    applying = true;
    toastError(
      instrument.applyRoutingRule(dimension.id).finally(() => {
        applying = false;
      })
    );
  }

  function useCurrentPosition(): void {
    if (draft.type === 'split') updateSplit({ threshold: instrument.stage.position(draft.axis) });
  }

  function swapRoutes(): void {
    if (draft.type === 'split') updateSplit({ lower: draft.upper, upper: draft.lower });
  }

  function routeOptionsExcept(route: string): { value: string; label: string }[] {
    return routeOptions.filter((option) => option.value !== route);
  }
</script>

<div class="min-w-0">
  <div class="flex min-h-ui-xs flex-wrap items-center gap-2">
    <h2 class="min-w-0 text-base text-fg">{displayName(dimension.id)}</h2>
    {#if changed}
      <div class="ml-auto flex items-center gap-2">
        <Button variant="ghost" size="xs" {disabled} onclick={reset}>Cancel</Button>
        <Button size="xs" loading={saving} {disabled} onclick={save}>Save rule</Button>
      </div>
    {/if}
  </div>
  <div class="grid grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)_auto] content-start items-center gap-x-2 gap-y-3 py-3">
    <div class="self-center text-base text-fg-muted">Rule</div>
    <div class="col-span-3">
      <div class="grid h-ui-sm w-full grid-cols-2 items-center rounded border border-input bg-canvas/50 p-0.5">
        <button
          type="button"
          {disabled}
          class={cn(
            'h-full w-full rounded-sm px-3 text-base transition-colors',
            draft.type === 'fixed' ? 'bg-element-selected text-fg shadow-sm' : 'text-fg-muted hover:text-fg'
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
            draft.type === 'split' ? 'bg-element-selected text-fg shadow-sm' : 'text-fg-muted hover:text-fg'
          )}
          onclick={() => selectType('split')}
        >
          Stage split
        </button>
      </div>
    </div>

    {#if draft.type === 'fixed'}
      <div class="self-center text-base text-fg-muted">Route</div>
      <div class="col-span-3">
        <Select
          value={draft.route}
          options={routeOptions}
          size="sm"
          class="w-full"
          {disabled}
          onchange={(route) => (draft = { type: 'fixed', route })}
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
                draft.axis === axis ? 'bg-element-selected text-fg shadow-sm' : 'text-fg-muted hover:text-fg'
              )}
              onclick={() => updateSplit({ axis: axis as 'x' | 'y' })}
            >
              {axis}
            </button>
          {/each}
        </div>
      </div>

      <div class="self-center text-base text-fg-muted">Threshold</div>
      {#key unit.value}
        <SpinBox
          model={{
            value: draft.threshold / unit.scale,
            onChange: (threshold) => updateSplit({ threshold: threshold * unit.scale }),
            step: 1 / unit.scale
          }}
          decimals={unit.decimals}
          numCharacters={9}
          suffix={unit.label}
          size="sm"
          class="col-span-2 w-full"
          {disabled}
        />
      {/key}
      <Button variant="secondary" size="xs" {disabled} onclick={useCurrentPosition}>
        Use current {draft.axis.toUpperCase()}
      </Button>

      <div class="self-center text-base text-fg-muted">Routes</div>
      <Select
        value={draft.lower}
        options={routeOptionsExcept(draft.upper)}
        prefix="<"
        size="sm"
        class="min-w-0"
        {disabled}
        onchange={(lower) => updateSplit({ lower })}
      />
      <Select
        value={draft.upper}
        options={routeOptionsExcept(draft.lower)}
        prefix="≥"
        size="sm"
        class="min-w-0"
        {disabled}
        onchange={(upper) => updateSplit({ upper })}
      />
      <Button variant="secondary" size="xs" {disabled} onclick={swapRoutes}>Swap</Button>
    {/if}
  </div>

  <div class="flex flex-wrap items-center gap-2 text-sm text-fg-muted">
    <span>
      {#if dimension.moving || applying}
        Switching…
      {:else}
        Current: {dimension.current != null ? displayName(dimension.current) : 'Unknown'}
        · Saved rule: {dimension.resolved != null ? displayName(dimension.resolved) : 'Unknown'}
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
        changed ||
        dimension.moving ||
        dimension.resolved == null ||
        dimension.current === dimension.resolved}
      title={changed ? 'Save or cancel rule changes before applying' : undefined}
      onclick={apply}
    >
      Apply rule
    </Button>
  </div>

  {#if instrument.mode === 'capture'}
    <p class="text-base text-fg-muted">Routing rules cannot be changed during capture.</p>
  {/if}
</div>
