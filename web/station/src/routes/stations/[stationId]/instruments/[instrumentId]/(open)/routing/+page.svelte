<script lang="ts">
  import { SvelteMap, SvelteSet } from 'svelte/reactivity';

  import { getOpenInstrument } from '$lib/context.svelte';
  import { reportFailure } from '$lib/core/failures';
  import {
    deviceLocked,
    deviceReady,
    type DiscreteAxisHandle,
    EnumeratedModel,
    NumericModel,
    type OpticalRouteConfig,
    type RoutingDimension
  } from '$lib/core/model';
  import { prefs } from '$lib/core/prefs';
  import { getSpatialUnit } from '$lib/core/spatial-units';
  import { cn, displayName } from '$lib/core/utils';
  import { issues, issueText, LEVEL_TEXT } from '$lib/features/issues';
  import { Badge, Button, Section, Select, SpinBox } from '$lib/kit';
  import { Crosshair } from '$lib/kit/icons';
  import { deviceHref } from '$lib/navigation';
  import PageHeader from '$lib/shell/PageHeader.svelte';

  const instrument = $derived.by(getOpenInstrument());
  const spatialUnit = $derived(prefs.spatialUnit.get());
  const unit = $derived(getSpatialUnit(spatialUnit));
  const pending = new SvelteMap<RoutingDimension, 'apply' | 'select'>();
  const movingWheels = new SvelteSet<string>();
  const profileFilters = $derived.by(() => {
    const filters: Record<string, string> = {};
    for (const channel of instrument.activeChannels)
      for (const filter of channel.filters) if (filter.filter) filters[filter.wheel.id] = filter.filter;
    return filters;
  });

  async function selectFilter(wheel: DiscreteAxisHandle, filter: string): Promise<void> {
    const current = instrument;
    if (!current || current.busy || current.edits.pending || movingWheels.has(wheel.id)) return;
    if (wheel.state?.is_moving || !deviceReady(wheel)) return;
    movingWheels.add(wheel.id);
    try {
      await wheel.select(filter);
    } finally {
      movingWheels.delete(wheel.id);
    }
  }

  /** Select a route by hand, or move back to the route the saved rule picks when the route is omitted. */
  function switchRoute(dimension: RoutingDimension, route?: string): void {
    const current = instrument;
    if (!current || current.busy || current.edits.pending || pending.has(dimension) || dimension.moving) return;
    if (
      route === undefined
        ? dimension.resolved == null || dimension.current === dimension.resolved
        : dimension.current === route
    )
      return;
    pending.set(dimension, route === undefined ? 'apply' : 'select');
    reportFailure(
      (route === undefined ? current.applyRoutingRule(dimension.id) : current.selectRoute(dimension.id, route)).finally(
        () => pending.delete(dimension)
      )
    );
  }

  function splitSide(dimension: RoutingDimension, route: string): string | null {
    if (!dimension.axis) return null;
    return route === 'lower' ? 'below' : 'above';
  }
</script>

{#snippet savedMark(label: string)}
  <span class="inline-block size-2 shrink-0 rounded-full bg-accent-fg" role="img" aria-label={label} title={label}
  ></span>
{/snippet}

<PageHeader items={[{ label: 'Routing' }]}>
  {#snippet trailing()}
    <span class="text-sm text-fg-faint">{instrument.routingDimensions.size}</span>
  {/snippet}
</PageHeader>
<div class="page-body">
  <div class="grid grid-cols-[minmax(--spacing(20),max-content)_minmax(0,1fr)_auto] gap-x-1 gap-y-3">
    {#if instrument.busy}
      <p class="col-span-full text-sm text-fg-muted">Filters and routes cannot be changed during capture.</p>
    {/if}
    {#if instrument.filterWheels.length}
      <Section id="filter-wheels" heading="Filter wheels" variant="raised" flush subgrid class="scroll-mt-3">
        {#snippet trailing()}<Badge>from profile channels</Badge>{/snippet}
        <div class="col-span-full grid grid-cols-subgrid items-center gap-y-2 px-2.5 pt-2.5 pb-3.5">
          {#each instrument.filterWheels as wheel (wheel.id)}
            {@const moving = Boolean(wheel.state?.is_moving) || movingWheels.has(wheel.id)}
            {@const current = wheel.labelAt(wheel.state?.position)}
            {@const saved = profileFilters[wheel.id]}
            {@const offProfile = saved != null && current != null && current !== saved}
            {@const found = issues.about({ device: wheel.id })}
            {@const disabled = deviceLocked(wheel, instrument) || instrument.edits.pending || moving}
            <a
              class="truncate pr-1 text-sm whitespace-nowrap text-fg-muted hover:text-fg"
              href={deviceHref({ stationId: instrument.stationId, instrumentId: instrument.id }, wheel.id)}
              >{displayName(wheel.id)}</a
            >
            <Select
              class={cn('min-w-0', !offProfile && 'col-span-2', found[0] && LEVEL_TEXT[found[0].level])}
              value={current}
              options={wheel.slots.flatMap((slot) => (slot.label == null ? [] : [slot.label]))}
              {disabled}
              loading={moving}
              placeholder={moving ? 'Moving…' : 'Unknown'}
              title={found.length ? issueText(found) : undefined}
              aria-label={`${displayName(wheel.id)} filter`}
              onChange={(filter) => reportFailure(selectFilter(wheel, filter))}
            >
              {#snippet trailing(filter)}
                {#if filter === saved}{@render savedMark('Active profile filter')}{/if}
              {/snippet}
            </Select>
            {#if offProfile}
              <Button
                variant="secondary"
                {disabled}
                title="The wheel is off the active profile's filter. Move it back."
                onclick={() => saved && reportFailure(selectFilter(wheel, saved))}>Back to profile</Button
              >
            {/if}
          {/each}
        </div>
      </Section>
    {/if}
    {#each instrument.routingDimensions.values() as dimension (dimension.id)}
      {@const assignments = (instrument.hal.optical_routing[dimension.id]?.routes ?? {}) as Record<
        string,
        OpticalRouteConfig
      >}
      {@const selectors = [...new Set(Object.values(assignments).flatMap((route) => Object.keys(route.selectors)))]}
      {@const model = dimension.model}
      {@const disabled = instrument.busy || pending.has(dimension)}
      {@const switching = dimension.moving || pending.has(dimension)}
      {@const hardwareDisabled = disabled || instrument.edits.pending || dimension.moving}
      {@const overridden =
        dimension.resolved != null && dimension.current != null && dimension.current !== dimension.resolved}
      {@const found = issues.about({ dimension: dimension.id })}
      {@const position = dimension.axis ? instrument.stage.axis(dimension.axis).position?.value : null}
      <Section
        id={`routing-${dimension.id}`}
        heading={displayName(dimension.id)}
        variant="raised"
        flush
        subgrid
        class="scroll-mt-3"
      >
        {#snippet trailing()}
          <Badge>{dimension.axis ? `split by stage ${dimension.axis.toUpperCase()}` : 'fixed choice'}</Badge>
        {/snippet}

        <div class="col-span-full grid grid-cols-subgrid items-center gap-y-2 p-2.5">
          <span class="pr-1 text-sm whitespace-nowrap text-fg-muted">Rule</span>
          {#key model}
            {#if model instanceof NumericModel}
              <div class="col-span-2 flex min-w-0 items-center">
                {#key unit.value}
                  <SpinBox
                    {model}
                    displayScale={unit.scale}
                    decimals={unit.decimals}
                    prefix={`${dimension.axis?.toUpperCase()} split`}
                    suffix={unit.label}
                    class="min-w-0 flex-1 rounded-r-none"
                    {disabled}
                  />
                {/key}
                <Button
                  variant="secondary"
                  size="icon-sm"
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
              <Select
                class="col-span-2"
                {model}
                formatLabel={dimension.routeLabel}
                {disabled}
                aria-label="Rule route"
              />
            {/if}
          {/key}

          <span class="pr-1 text-sm whitespace-nowrap text-fg-muted">Now</span>
          <Select
            class={cn('min-w-0 tabular-nums', !overridden && 'col-span-2', found[0] && LEVEL_TEXT[found[0].level])}
            value={switching ? null : dimension.current}
            options={dimension.routes}
            formatLabel={dimension.routeLabel}
            disabled={hardwareDisabled}
            placeholder={switching ? 'Switching…' : 'Unknown'}
            loading={switching}
            title={found.length ? issueText(found) : undefined}
            aria-label="Hardware route"
            onChange={(route) => switchRoute(dimension, route)}
          >
            {#snippet trailing(route)}
              {#if route === dimension.resolved}{@render savedMark('Selected by rule')}{/if}
            {/snippet}
          </Select>
          {#if overridden}
            <Button
              variant="secondary"
              loading={pending.get(dimension) === 'apply'}
              disabled={hardwareDisabled}
              title="The hardware is off the rule's route. Move it to the route the rule picks."
              onclick={() => switchRoute(dimension)}>Back to rule</Button
            >
          {/if}
        </div>

        {#if selectors.length}
          <div class="col-span-full overflow-x-auto border-t border-line-faint">
            <table class="w-full text-sm">
              <thead>
                <tr>
                  <th scope="col" class="px-2.5 py-1.5 text-left font-normal text-fg-muted">Selector</th>
                  {#each dimension.routes as route (route)}
                    {@const side = splitSide(dimension, route)}
                    <th
                      scope="col"
                      class={cn(
                        'px-2.5 py-1.5 text-left font-normal text-fg',
                        route === dimension.current && 'bg-tint'
                      )}
                      title={route === dimension.current ? 'The hardware is on this route' : undefined}
                    >
                      {dimension.routeLabel(route)}{#if side}<span class="ml-1 text-fg-muted">({side})</span>{/if}
                    </th>
                  {/each}
                </tr>
              </thead>
              <tbody>
                {#each selectors as selector (selector)}
                  <tr class="border-t border-line-faint">
                    <th scope="row" class="px-2.5 py-1.5 text-left font-normal text-fg-muted">
                      {displayName(selector)}
                    </th>
                    {#each dimension.routes as route (route)}
                      <td class={cn('px-2.5 py-1.5 text-fg', route === dimension.current && 'bg-tint')}>
                        {assignments[route]?.selectors[selector] ?? '—'}
                      </td>
                    {/each}
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </Section>
    {:else}
      <p class="col-span-full text-sm text-fg-muted">This instrument has no optical routing.</p>
    {/each}
  </div>
</div>
