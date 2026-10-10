<script lang="ts">
  import { SvelteMap } from 'svelte/reactivity';

  import { Crosshair } from '$lib/icons';
  import { Button, Select } from '$lib/kit';
  import { EnumeratedModel, type Instrument, NumericModel, type RoutingDimension } from '$lib/model';
  import { prefs } from '$lib/prefs';
  import { Select as EnumeratedSelect } from '$lib/prop/enumerated';
  import { SpinBox } from '$lib/prop/numeric';
  import { getSpatialUnit } from '$lib/spatial-units';
  import { displayName, toastError } from '$lib/utils';

  let { instrument }: { instrument: Instrument } = $props();
  const unit = $derived(getSpatialUnit(prefs.spatialUnit.get()));
  const saving = $derived(instrument.edits.busy);
  const pending = new SvelteMap<RoutingDimension, 'apply' | 'select'>();

  /** Select an explicit hardware route, or apply the persisted rule when omitted. */
  function switchRoute(dimension: RoutingDimension, route?: string): void {
    const current = instrument;
    if (!current || current.mode === 'capture' || current.edits.busy || pending.has(dimension) || dimension.moving)
      return;
    if (
      route === undefined
        ? dimension.resolved == null || dimension.current === dimension.resolved
        : dimension.current === route
    )
      return;
    pending.set(dimension, route === undefined ? 'apply' : 'select');
    toastError(
      (route === undefined ? current.applyRoutingRule(dimension.id) : current.selectRoute(dimension.id, route)).finally(
        () => pending.delete(dimension)
      )
    );
  }
</script>

<div class="flex flex-col gap-4">
  {#each instrument.routingDimensions.values() as dimension (dimension.id)}
    {@const model = dimension.model}
    {@const applying = pending.get(dimension) === 'apply'}
    {@const disabled = instrument.mode === 'capture' || pending.has(dimension)}
    {@const hardwareDisabled = disabled || saving || dimension.moving}
    {@const switching = dimension.moving || pending.has(dimension)}
    {@const position = dimension.axis ? instrument.stage.axis(dimension.axis).position?.value : null}
    {@const options = dimension.routes.map((route) => ({ value: route, label: dimension.routeLabel(route) }))}
    <section
      id={`routing-${dimension.id}`}
      class="min-w-0 scroll-mt-4 space-y-3 rounded-lg border border-line-faint p-3"
      aria-labelledby={`routing-${dimension.id}-heading`}
    >
      <div class="flex flex-wrap items-center gap-2">
        <h2 id={`routing-${dimension.id}-heading`} class="min-w-0 text-base text-fg">
          {displayName(dimension.id)}
        </h2>
        <div role="group" aria-label="Hardware route" class="ml-auto min-w-0">
          <Select
            size="xs"
            class="w-42 max-w-full tabular-nums"
            value={switching ? '' : (dimension.current ?? '')}
            {options}
            disabled={hardwareDisabled}
            placeholder={switching ? 'Switching…' : 'Unknown'}
            loading={switching}
            onchange={(route) => switchRoute(dimension, route)}
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
      </div>

      <div class="flex flex-wrap items-center gap-2">
        {#key model}
          {#if model instanceof NumericModel}
            <div class="flex min-w-0 flex-1 basis-48 items-center">
              {#key unit.value}
                <SpinBox
                  {model}
                  displayScale={unit.scale}
                  decimals={unit.decimals}
                  numCharacters={9}
                  prefix={`${dimension.axis?.toUpperCase()} split`}
                  suffix={unit.label}
                  size="xs"
                  class="min-w-0 flex-1 rounded-r-none"
                  align="right"
                  {disabled}
                />
              {/key}
              <Button
                variant="secondary"
                size="icon-xs"
                class="-ml-px rounded-l-none text-fg-muted"
                disabled={disabled || position == null}
                aria-label="Use current stage position"
                title="Set the split to the current stage position"
                onclick={() => {
                  if (!disabled && model instanceof NumericModel && position != null) model.patch(position);
                }}
              >
                <Crosshair class="size-3.5" />
              </Button>
            </div>
          {:else if model instanceof EnumeratedModel}
            <div role="group" aria-label="Rule route" class="min-w-0 flex-1 basis-48">
              <EnumeratedSelect prefix="Rule" size="xs" {model} formatLabel={dimension.routeLabel} {disabled} />
            </div>
          {/if}
        {/key}
        <Button
          variant="secondary"
          size="xs"
          class="font-normal"
          loading={saving || applying}
          disabled={hardwareDisabled || dimension.resolved == null || dimension.current === dimension.resolved}
          aria-label={saving ? 'Saving rule' : applying ? 'Applying rule' : 'Apply rule'}
          title={saving
            ? 'Saving rule…'
            : applying
              ? 'Applying rule…'
              : 'Move hardware to the route selected by the rule'}
          onclick={() => switchRoute(dimension)}
        >
          Apply rule
        </Button>
      </div>
      {#if instrument.mode === 'capture'}
        <p class="text-sm text-fg-muted">Routing cannot be changed during capture.</p>
      {/if}
    </section>
  {:else}
    <p class="text-base text-fg-muted">This instrument has no optical routing rules.</p>
  {/each}
</div>
