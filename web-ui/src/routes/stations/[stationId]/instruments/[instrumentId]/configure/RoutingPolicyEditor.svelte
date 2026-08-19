<script lang="ts">
  import { watch } from 'runed';

  import { Button, Select } from '$lib/kit';
  import type { Instrument, OpticalRoutingPolicy, RoutingDimension, SplitOpticalRoutingPolicy } from '$lib/model';
  import { SpinBox } from '$lib/prop/numeric';
  import { cn, displayName, toastError } from '$lib/utils';

  import { asFixedPolicy, asSplitPolicy, clonePolicy } from './policy';

  interface Props {
    instrument: Instrument;
    dimension: RoutingDimension;
  }

  let { instrument, dimension }: Props = $props();

  let draft = $state<OpticalRoutingPolicy>({ type: 'fixed', route: '' });
  let sourceKey = $state('');
  let saving = $state(false);

  const routes = $derived(dimension.policyRoutes);
  const routeOptions = $derived(routes.map((route) => ({ value: route, label: displayName(route) })));
  const canSplit = $derived(routes.length >= 2);
  const changed = $derived(JSON.stringify(draft) !== JSON.stringify(dimension.policy));
  const disabled = $derived(instrument.mode === 'capture' || saving);

  watch(
    () => `${dimension.id}:${JSON.stringify(dimension.policy)}`,
    (key) => {
      if (key !== sourceKey) {
        sourceKey = key;
        draft = clonePolicy(dimension.policy);
      }
    }
  );

  function selectType(type: OpticalRoutingPolicy['type']): void {
    if (type === draft.type) return;
    draft =
      type === 'fixed'
        ? asFixedPolicy(draft, routes, dimension.target)
        : asSplitPolicy(draft, routes, instrument.stage.position('x'));
  }

  function updateSplit(changes: Partial<Omit<SplitOpticalRoutingPolicy, 'type'>>): void {
    if (draft.type === 'split') draft = { ...draft, ...changes };
  }

  function reset(): void {
    draft = clonePolicy(dimension.policy);
  }

  function apply(): void {
    if (!changed || disabled) return;
    saving = true;
    const request = instrument.updateOpticalRoutingPolicy(dimension.id, draft);
    toastError(request);
    void request.then(
      () => {
        saving = false;
      },
      () => {
        saving = false;
      }
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

<div class="rounded-sm border border-border bg-card/50">
  <div
    class="grid h-48 grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)_auto] content-start items-center gap-x-2 gap-y-3 overflow-y-auto px-4 py-4"
  >
    <div class="self-center text-base text-fg-muted">Policy</div>
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
          title={canSplit ? undefined : 'A split policy requires at least two supported routes'}
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
      <SpinBox
        model={{
          value: draft.threshold / 1000,
          onChange: (threshold) => updateSplit({ threshold: threshold * 1000 }),
          step: 0.001
        }}
        decimals={4}
        numCharacters={9}
        suffix="mm"
        size="sm"
        class="col-span-2 w-full"
        {disabled}
      />
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

  <div class="flex items-center gap-2 border-t border-border px-4 py-2.5">
    {#if instrument.mode === 'capture'}
      <span class="text-base text-fg-muted">Routing policies cannot be changed during capture.</span>
    {/if}
    <div class="ml-auto flex items-center gap-2">
      <Button variant="ghost" size="xs" disabled={!changed || disabled} onclick={reset}>Cancel</Button>
      <Button size="xs" loading={saving} disabled={!changed || disabled} onclick={apply}>Apply policy</Button>
    </div>
  </div>
</div>
