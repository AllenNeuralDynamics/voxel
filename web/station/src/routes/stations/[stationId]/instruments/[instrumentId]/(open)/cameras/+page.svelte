<script lang="ts">
  import { getOpenInstrument } from '$lib/context.svelte';
  import { deviceLocked, deviceReady, EnumeratedModel, NumericModel, type Prop } from '$lib/core/model';
  import { deviceIdentity } from '$lib/features/devices/snippets.svelte';
  import LinkToggle from '$lib/features/imaging/LinkToggle.svelte';
  import PropertyDivergenceDot from '$lib/features/imaging/PropertyDivergenceDot.svelte';
  import { issues, LEVEL_TEXT } from '$lib/features/issues';
  import { deviceHref } from '$lib/navigation';
  import PageHeader from '$lib/shell/PageHeader.svelte';
  import { Checkbox, NumberBox, RadioBar, Section, Select, Slider } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { displayName } from '@voxel/kit/format';

  type Setting = {
    name: string;
    deviceId: string;
    prop: Prop | undefined;
    locked: boolean;
    format?: (value: unknown) => string;
    select?: boolean;
  };

  const instrument = $derived.by(getOpenInstrument());

  function reading(value: unknown): string {
    return typeof value === 'number' && Number.isFinite(value) ? Number(value.toPrecision(5)).toString() : '—';
  }

  function fixed(value: number | null | undefined, decimals = 1): string {
    return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(decimals) : '—';
  }

  function valueText(value: unknown): string {
    return typeof value === 'number' ? reading(value) : value == null ? '—' : String(value);
  }

  /** A slider needs both limits. Without them, the native input falls back to 0 to 100. */
  function hasRange({ min, max }: NumericModel): boolean {
    return min != null && max != null && Number.isFinite(min) && Number.isFinite(max) && max > min;
  }
</script>

{#snippet setting({ name, deviceId, prop, locked, format = valueText, select = false }: Setting)}
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
      {#if prop.access !== 'rw'}
        <span
          class="col-span-2 flex items-center justify-end gap-1 font-mono text-sm tabular-nums"
          title={prop.info.desc}
        >
          <span class="text-fg">{format(prop.value)}</span><span class="text-fg-muted">{units}</span>
        </span>
      {:else if prop.model instanceof EnumeratedModel && (select || prop.model.options.length > 4)}
        <Select
          class="col-span-2"
          model={prop.model as EnumeratedModel<string | number>}
          formatLabel={(value) => (units ? `${format(value)} ${units}` : format(value))}
          disabled={!editable}
          aria-label={fullName}
        />
      {:else if prop.model instanceof EnumeratedModel}
        <RadioBar
          class="col-span-2"
          model={prop.model as EnumeratedModel<string | number>}
          formatLabel={format}
          disabled={!editable}
          aria-label={fullName}
        />
      {:else if prop.model instanceof NumericModel}
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
      {/if}
    </div>
  {/if}
{/snippet}

<PageHeader items={[{ label: 'Cameras' }]}>
  {#snippet trailing()}
    <span class="text-sm text-fg-faint">{instrument.cameras.size}</span>
  {/snippet}
</PageHeader>
<div class="page-body">
  <div class="grid grid-cols-1 gap-3">
    {#if instrument.links.candidates.length}
      {@const links = instrument.links.candidates}
      <Section variant="raised">
        {#snippet heading()}
          <span title="A linked property changes on all its cameras at once">Linked properties</span>
        {/snippet}
        {#snippet trailing()}
          <span class="text-sm text-fg-muted tabular-nums"
            >{links.filter((link) => instrument.links.isLinked(link.key)).length} of {links.length}</span
          >
        {/snippet}
        <div class="grid grid-cols-[repeat(auto-fill,minmax(12rem,1fr))] gap-x-3">
          {#each links as link (link.key)}
            <label
              class="flex min-w-0 items-center gap-2 py-1 text-sm text-fg"
              title={link.members.map((member) => displayName(member.device.id)).join(', ')}
            >
              <Checkbox
                value={instrument.links.isLinked(link.key)}
                disabled={instrument.busy}
                onChange={(linked) => instrument.links.setLinked(link.key, linked)}
              />
              <span class="min-w-0 truncate">{link.label}</span>
            </label>
          {/each}
        </div>
      </Section>
    {/if}
    {#each instrument.cameras.values() as camera (camera.id)}
      {@const channel = instrument.activeChannels.find((channel) => channel.camera.id === camera.id)}
      {@const streaming = camera.mode === 'PREVIEW' || camera.mode === 'ACQUISITION'}
      {@const idle = deviceReady(camera) && camera.mode === 'IDLE'}
      {@const info = deviceReady(camera) && streaming ? camera.streamInfo : undefined}
      {@const dropIssue = issues.about({ device: camera.id }).find(({ code }) => code === 'camera.dropped_frames')}
      {@const frame = camera.connected ? camera.frameSizePx : null}
      {@const sizeMb = camera.connected ? camera.frameSizeMb?.value : undefined}
      {@const buffer = info ? camera.bufferFill : null}
      {@const bufferPercent = buffer == null ? null : Math.max(0, Math.min(100, buffer * 100))}
      {@const locked = deviceLocked(camera, instrument)}
      {@const status = !camera.connected
        ? 'Disconnected'
        : camera.error
          ? 'Error'
          : camera.mode
            ? displayName(camera.mode.toLowerCase())
            : 'Unknown'}
      <Section variant="raised">
        {#snippet heading()}
          <a
            href={deviceHref({ stationId: instrument.stationId, instrumentId: instrument.id }, camera.id)}
            class="flex min-w-0 items-center gap-2 rounded-sm hover:underline focus-visible:outline-2 focus-visible:outline-focus"
            title="Open camera device"
          >
            {@render deviceIdentity(displayName(camera.id), channel)}
          </a>
        {/snippet}
        {#snippet trailing()}
          <div
            class="flex h-5 shrink-0 divide-x divide-control-line overflow-hidden rounded-sm border border-control-line bg-element-bg font-mono text-[10px] tabular-nums"
          >
            <span
              class="flex w-5 shrink-0 items-center justify-center"
              role="img"
              aria-label={status}
              title={camera.error || status}
            >
              <span
                class={cn(
                  'size-2 rounded-full',
                  !camera.connected
                    ? 'bg-fg-faint'
                    : camera.error
                      ? 'bg-danger-fg'
                      : camera.mode === 'PREVIEW'
                        ? 'bg-accent-fg'
                        : camera.mode === 'ACQUISITION'
                          ? 'bg-success-fg'
                          : 'bg-fg-muted/40'
                )}
              ></span>
            </span>
          </div>
        {/snippet}

        <div class="grid grid-cols-[minmax(--spacing(20),max-content)_minmax(0,1fr)_auto] gap-x-1 gap-y-2">
          {@render setting({
            name: 'Exposure',
            deviceId: camera.id,
            prop: camera.getProp('exposure_time_ms'),
            locked
          })}
          {@render setting({
            name: 'Frame rate',
            deviceId: camera.id,
            prop: camera.getProp('frame_rate_hz'),
            locked
          })}
          {@render setting({
            name: 'Binning',
            deviceId: camera.id,
            prop: camera.getProp('binning'),
            locked,
            format: (value) => `${value}×${value}`
          })}
          {@render setting({
            name: 'Pixel format',
            deviceId: camera.id,
            prop: camera.getProp('pixel_format'),
            locked,
            select: true
          })}
        </div>

        <div class="space-y-2">
          <div
            class="grid min-w-0 grid-cols-[minmax(0,1fr)_--spacing(24)] overflow-hidden rounded-sm border border-control-line bg-element-bg font-mono text-[10px] tabular-nums"
          >
            <span class="flex h-6 min-w-0 items-center gap-1 px-1.5" title="Frame dimensions">
              <span class="truncate">{frame ? `${frame.x} × ${frame.y}` : '— × —'}</span>
              <span class="text-fg-muted">px</span>
            </span>
            <span
              class="flex h-6 items-center justify-end gap-1 border-l border-control-line px-1.5"
              title="Frame size"
            >
              <span class="truncate">{fixed(sizeMb)}</span><span class="text-fg-muted">MB</span>
            </span>
          </div>
          <div
            class="grid grid-cols-[minmax(0,2.35fr)_minmax(0,0.8fr)_minmax(0,1.05fr)] divide-x divide-control-line overflow-hidden rounded-sm border border-control-line bg-element-bg font-mono text-[10px] tabular-nums"
            role="group"
            aria-label="Live capture telemetry"
          >
            <div class="flex h-6 min-w-0 items-center justify-between gap-1 px-1">
              <div class="flex min-w-0 flex-1 items-center gap-0.5" title="Capture buffer fill">
                <span class="mr-1 shrink-0 font-sans text-fg-muted">Buffer</span>
                <div
                  class={cn('flex h-1.5 min-w-0 flex-1 gap-px', idle && 'invisible')}
                  role="progressbar"
                  aria-label="Capture buffer fill"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={bufferPercent ?? undefined}
                  aria-valuetext={idle ? 'Idle' : bufferPercent == null ? 'Unavailable' : `${fixed(bufferPercent, 0)}%`}
                >
                  {#each [0, 1, 2, 3, 4] as tick (tick)}
                    <span class="relative min-w-0 flex-1 overflow-hidden rounded-[1px] bg-fg/10">
                      <span
                        class="absolute inset-y-0 left-0 bg-fg/40"
                        style:width={`${Math.max(0, Math.min(100, ((bufferPercent ?? 0) - tick * 20) * 5))}%`}
                      ></span>
                    </span>
                  {/each}
                </div>
                <span class="flex w-[4.5ch] shrink-0 items-center justify-end gap-0.5"
                  ><span>{idle ? '' : fixed(bufferPercent, 0)}</span><span
                    class={cn('text-fg-muted', idle && 'invisible')}>%</span
                  ></span
                >
              </div>
              <span class="flex w-[9ch] shrink-0 items-center justify-end gap-0.5" title="Dropped frames">
                <span class={cn('truncate', dropIssue && LEVEL_TEXT[dropIssue.level])}
                  >{idle ? '' : fixed(info?.dropped_frames, 0)}</span
                >
                <span class={cn('text-fg-muted', idle && 'invisible')}>dropped</span>
              </span>
            </div>
            <span class="flex h-6 min-w-0 items-center justify-end gap-0.5 px-1" title="Measured frame rate">
              <span class="truncate">{idle ? '' : fixed(info?.frame_rate_fps)}</span><span class="text-fg-muted"
                >fps</span
              >
            </span>
            <span
              class="flex h-6 min-w-0 items-center justify-end gap-0.5 bg-element-active px-1"
              title="Measured data rate"
            >
              <span class="truncate">{idle ? '' : fixed(info?.data_rate_mbs)}</span><span class="text-fg-muted"
                >MB/s</span
              >
            </span>
          </div>
        </div>
      </Section>
    {:else}
      <p class="text-sm text-fg-muted">No cameras available.</p>
    {/each}
  </div>
</div>
