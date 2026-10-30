<script lang="ts">
  import { getOpenInstrument } from '$lib/context.svelte';
  import { reportFailure } from '$lib/core/failures';
  import { type AxisHandle, deviceLocked, NumericModel, type Prop } from '$lib/core/model';
  import { prefs } from '$lib/core/prefs';
  import { formatSpatialValue, getSpatialUnit } from '$lib/core/spatial-units';
  import { cn, displayName } from '$lib/core/utils';
  import LinkToggle from '$lib/features/imaging/LinkToggle.svelte';
  import PropertyDivergenceDot from '$lib/features/imaging/PropertyDivergenceDot.svelte';
  import StageGizmo from '$lib/features/stage/StageGizmo.svelte';
  import { Button, NumberBox, Section, Slider } from '$lib/kit';
  import { Loader } from '$lib/kit/icons';
  import { deviceHref } from '$lib/navigation';
  import PageHeader from '$lib/shell/PageHeader.svelte';

  type Axis = 'x' | 'y' | 'z';
  type GizmoView = 'iso' | 'xy' | 'xz' | 'yz';

  const AXES: readonly Axis[] = ['x', 'y', 'z'];
  const GIZMO_VIEWS: readonly GizmoView[] = ['iso', 'xy', 'xz', 'yz'];
  const GIZMO_TITLES: Record<GizmoView, string> = {
    iso: 'View all 3 axes',
    xy: 'View down Z',
    xz: 'View down Y',
    yz: 'View down X'
  };
  const GIZMO_AXES: Record<GizmoView, Record<Axis, boolean>> = {
    iso: { x: true, y: true, z: true },
    xy: { x: true, y: true, z: false },
    xz: { x: true, y: false, z: true },
    yz: { x: false, y: true, z: true }
  };
  const AXIS_TAGS: Record<Axis, string> = {
    x: 'bg-axis-x-tint text-axis-x',
    y: 'bg-axis-y-tint text-axis-y',
    z: 'bg-axis-z-tint text-axis-z'
  };
  const AXIS_TEXT: Record<Axis, string> = { x: 'text-axis-x', y: 'text-axis-y', z: 'text-axis-z' };

  const instrument = $derived.by(getOpenInstrument());
  const stage = $derived(instrument.stage);
  const unit = $derived(getSpatialUnit(prefs.spatialUnit.get()));
  let gizmoView = $state<GizmoView>('iso');

  function reading(value: unknown): string {
    return typeof value === 'number' && Number.isFinite(value) ? Number(value.toPrecision(5)).toString() : '—';
  }

  function spatial(value: number | null | undefined): string {
    return value == null ? '—' : formatSpatialValue(value, unit.value);
  }

  /** A slider needs both limits. Without them, the native input falls back to 0 to 100. */
  function hasRange({ min, max }: NumericModel): boolean {
    return min != null && max != null && Number.isFinite(min) && Number.isFinite(max) && max > min;
  }

  // Moves go through the stage, so the gizmo and the stage view show the target too.
  function move(axis: Axis, position: number): void {
    reportFailure(instrument.stage.moveTo({ [axis]: position }));
  }

  function goHome(handle: AxisHandle): void {
    reportFailure(handle.runCommand('go_home', [], { wait: false }));
  }
</script>

{#snippet setting(name: string, deviceId: string, prop: Prop | undefined, locked: boolean)}
  {#if prop}
    {@const fullName = prop.info.label ?? name}
    {@const units = prop.info.units ?? ''}
    {@const editable = !locked && prop.access === 'rw'}
    <div class="col-span-full grid h-ui-sm grid-cols-subgrid items-stretch" role="group" aria-label={name}>
      <span class="flex items-center justify-between gap-1 pr-1 text-sm whitespace-nowrap text-fg-muted">
        <span class="flex min-w-0 items-center gap-1">
          {name}
          <PropertyDivergenceDot {instrument} {deviceId} property={prop.info.name} />
        </span>
        <LinkToggle {instrument} {deviceId} property={prop.info.name} />
      </span>
      {#if prop.model instanceof NumericModel && prop.access === 'rw'}
        <div class="min-w-0">
          {#if hasRange(prop.model)}
            <Slider variant="bar" model={prop.model} disabled={!editable} aria-label={fullName} />
          {/if}
        </div>
        <NumberBox
          model={prop.model}
          suffix={units || undefined}
          disabled={!editable}
          title={prop.info.desc}
          aria-label={fullName}
        />
      {:else}
        <span
          class="col-span-2 flex items-center justify-end gap-1 font-mono text-sm tabular-nums"
          title={prop.info.desc}
        >
          <span class="text-fg">{reading(prop.value)}</span><span class="text-fg-muted">{units}</span>
        </span>
      {/if}
    </div>
  {/if}
{/snippet}

<PageHeader items={[{ label: 'Stage' }]} />
<div class="page-body">
  <div class="grid grid-cols-1 gap-3">
    {#each AXES as axis (axis)}
      {@const handle = stage.axis(axis)}
      {@const moving = stage.moving(axis)}
      {@const lower = handle.lowerLimit?.value}
      {@const upper = handle.upperLimit?.value}
      {@const home = handle.getProp('home')}
      {@const locked = deviceLocked(handle, instrument)}
      <Section variant="raised">
        {#snippet heading()}
          <span class="flex min-w-0 items-center gap-2">
            <span
              class={cn(
                'flex size-5 shrink-0 items-center justify-center rounded-sm text-sm font-medium uppercase',
                AXIS_TAGS[axis]
              )}
              aria-hidden="true">{axis}</span
            >
            <a
              href={deviceHref({ stationId: instrument.stationId, instrumentId: instrument.id }, handle.id)}
              class="min-w-0 truncate rounded-sm text-base text-fg/80 hover:underline focus-visible:outline-2 focus-visible:outline-focus"
              title="Open axis device">{displayName(handle.id)}</a
            >
          </span>
        {/snippet}
        {#snippet trailing()}
          <span class="flex size-3 shrink-0 items-center justify-center">
            {#if moving}
              <span role="status" aria-label="Moving" class="animate-in delay-250 fill-mode-backwards fade-in"
                ><Loader class="size-3 animate-spin text-fg-muted" /></span
              >
            {/if}
          </span>
        {/snippet}
        <div class="grid grid-cols-[minmax(--spacing(20),max-content)_minmax(0,1fr)_auto] gap-x-1 gap-y-2">
          <div class="col-span-full grid h-ui-sm grid-cols-subgrid items-stretch" role="group" aria-label="Position">
            <span class="flex items-center pr-1 text-sm whitespace-nowrap text-fg-muted">Position</span>
            <div class="min-w-0">
              {#if lower != null && upper != null && upper > lower}
                <Slider
                  variant="bar"
                  value={handle.position?.value ?? lower}
                  min={lower}
                  max={upper}
                  onChange={(position) => move(axis, position)}
                  disabled={locked}
                  aria-label={`${axis.toUpperCase()} position`}
                />
              {/if}
            </div>
            {#key unit.value}
              <NumberBox
                value={handle.position?.value}
                min={lower}
                max={upper}
                step={unit.step * unit.scale}
                bigStep={unit.bigStep * unit.scale}
                displayScale={unit.scale}
                decimals={unit.decimals}
                suffix={unit.label}
                onChange={(position) => move(axis, position)}
                disabled={locked}
                aria-label={`${axis.toUpperCase()} position`}
              />
            {/key}
          </div>
          {@render setting('Speed', handle.id, handle.getProp('speed'), locked)}
          {@render setting('Acceleration', handle.id, handle.getProp('acceleration'), locked)}
          {@render setting('Backlash', handle.id, handle.getProp('backlash'), locked)}
          <div class="col-span-full grid h-ui-sm grid-cols-subgrid items-stretch" role="group" aria-label="Limits">
            <span class="flex items-center pr-1 text-sm whitespace-nowrap text-fg-muted">Limits</span>
            <span class="col-span-2 flex items-center justify-end gap-1 font-mono text-sm tabular-nums">
              <span class="text-fg">{spatial(lower)} – {spatial(upper)}</span><span class="text-fg-muted"
                >{unit.label}</span
              >
            </span>
          </div>
          {#if home}
            <div class="col-span-full grid h-ui-sm grid-cols-subgrid items-stretch" role="group" aria-label="Home">
              <span class="flex items-center pr-1 text-sm whitespace-nowrap text-fg-muted">Home</span>
              <span class="flex items-center justify-end">
                <Button variant="quiet" size="xs" disabled={locked} onclick={() => goHome(handle)}>Go home</Button>
              </span>
              <span class="flex items-center justify-end gap-1 font-mono text-sm tabular-nums" title={home.info.desc}>
                <span class="text-fg">{spatial(typeof home.value === 'number' ? home.value : null)}</span><span
                  class="text-fg-muted">{unit.label}</span
                >
              </span>
            </div>
          {/if}
        </div>
      </Section>
    {/each}
  </div>
</div>
<div class="h-56 shrink-0 border-t border-line-faint px-4 py-2">
  <div class="flex h-full max-w-4xl items-center justify-around gap-3">
    <fieldset class="flex shrink-0 flex-col gap-0.5">
      <legend class="sr-only">Gizmo view</legend>
      {#each GIZMO_VIEWS as view (view)}
        {@const picked = view === gizmoView}
        <label
          class={cn(
            'flex h-6 w-9 cursor-pointer items-center justify-center rounded-sm font-mono text-sm transition-colors has-focus-visible:outline-2 has-focus-visible:outline-focus',
            picked ? 'bg-element-selected' : 'opacity-60 hover:bg-element-hover hover:opacity-100'
          )}
          title={GIZMO_TITLES[view]}
        >
          <input type="radio" name="gizmo-view" value={view} bind:group={gizmoView} class="sr-only" />
          {#if view === 'iso'}
            <span class="text-fg">3D</span>
          {:else}
            {#each [...view] as Axis[] as axis (axis)}
              <span class={AXIS_TEXT[axis]}>{axis.toUpperCase()}</span>
            {/each}
          {/if}
        </label>
      {/each}
    </fieldset>
    <StageGizmo {stage} shown={GIZMO_AXES[gizmoView]} />
  </div>
</div>
