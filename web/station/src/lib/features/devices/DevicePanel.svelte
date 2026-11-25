<script lang="ts">
  import type { Component, Snippet } from 'svelte';
  import type { ClassValue } from 'svelte/elements';

  import { getInstrumentSelection } from '$lib/context.svelte';
  import { DiscreteAxis, LinearAxis } from '$lib/core/device.svelte';
  import type { OperationParam, PropValue } from '$lib/core/types';
  import {
    Button,
    Choice,
    Dialog,
    NumberBox,
    ObjectView,
    Popover,
    RadioBar,
    Ruler,
    Section,
    Select,
    Switch,
    TextBox
  } from '@voxel/kit';
  import { displayName } from '@voxel/kit/format';
  import { Check, ChevronRight, X } from '@voxel/kit/icons';

  import { DeviceSheet, type DeviceRow, type Pin } from './device-sheet.svelte';
  import LightPathSection from './LightPathSection.svelte';

  let { id }: { id: string } = $props();

  const selection = getInstrumentSelection();
  const sheet = new DeviceSheet(
    () => id,
    () => selection.instrument,
    () => selection.session
  );
  const { plain, text, size } = DeviceSheet;
  const stage = $derived(
    Object.entries(selection.instrument?.config?.stage ?? {}).find(([, axis]) => axis.device === id)
  );
  const axis = $derived(sheet.device instanceof LinearAxis ? sheet.device : undefined);
  const slots = $derived(sheet.device instanceof DiscreteAxis ? sheet.device : undefined);
  // The position the ruler was moved to; the device reports where it is as it moves there.
  let target = $state<number | null>(null);
  const PINS_SHOWN = 8;
  let allPins = $state(false);
  // Wired pins first, each part in the device's own order.
  const pins = $derived(
    sheet.pins.toSorted(
      (a, b) =>
        Number((sheet.instrument?.wires.ends(id, b.name).length ?? 0) > 0) -
        Number((sheet.instrument?.wires.ends(id, a.name).length ?? 0) > 0)
    )
  );
  const shownPins = $derived(allPins ? pins : pins.slice(0, PINS_SHOWN));

  /** The pin at the other end of a wire, as its device reports it; else the opposite direction and the same kind. */
  function farPin(device: string, name: string, near: Pin): { direction: string; kind: string } {
    const reported = (sheet.session?.device(device)?.prop('pins')?.value as Pin[] | undefined)?.find(
      (pin) => pin.name === name
    );
    return reported ?? { direction: near.direction === 'in' ? 'out' : 'in', kind: near.kind };
  }

  const SETTINGS = 'grid grid-cols-[minmax(0,1fr)_8.5rem_6rem] items-center gap-x-2';
  const GRID = 'grid auto-rows-[minmax(var(--ui-sm),auto)] items-center gap-y-1.5 frame-tinted px-2.5 py-2';
</script>

{#snippet item(label: string, Mark: Component, run: () => void)}
  <button
    type="button"
    class="flex h-ui-sm w-full cursor-pointer items-center justify-between gap-3 rounded-sm px-2 text-left hover:bg-element-hover focus-visible:bg-element-hover focus-visible:outline-none"
    onclick={run}
  >
    {label}<Mark class="size-3.5" aria-hidden="true" />
  </button>
{/snippet}

{#snippet keep(list: DeviceRow[], label: string, trigger: Snippet, extra: ClassValue)}
  {@const removing = list.filter((row) => sheet.removable(row))}
  <Popover.Root>
    <Popover.Trigger
      class={[
        'flex h-ui-xs w-full cursor-pointer items-center justify-end gap-2 rounded-sm px-1.5 text-right tabular-nums hover:bg-element-hover focus-visible:bg-element-hover focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50',
        extra
      ]}
      aria-label={label}
      disabled={sheet.running}
    >
      {@render trigger()}
    </Popover.Trigger>
    <Popover.Content class="flex w-44 flex-col gap-px p-1 text-sm" side="bottom" align="end" sideOffset={4}>
      {@render item('Save to profile', Check, () => sheet.saveToProfile(list))}
      {#if list.every((row) => sheet.inProfile(row))}
        {@render item('Restore from profile', Check, () => sheet.restoreFromProfile(list))}
      {/if}
      {#if removing.length > 0}
        {@render item('Remove from profile', X, () => sheet.removeFromProfile(removing))}
      {/if}
    </Popover.Content>
  </Popover.Root>
{/snippet}

{#snippet control(row: DeviceRow, prop: PropValue)}
  {#if prop.options && prop.options.length <= 4}
    <RadioBar
      value={prop.value as string}
      options={prop.options as string[]}
      disabled={sheet.running}
      aria-label={row.label}
      class="w-full"
      onChange={(value) => sheet.set(row.name, value)}
    />
  {:else if prop.options}
    <Select
      value={prop.value as string}
      options={prop.options as string[]}
      disabled={sheet.running}
      aria-label={row.label}
      class="w-full"
      onChange={(value) => sheet.set(row.name, value)}
    />
  {:else if typeof prop.value === 'boolean'}
    <Switch
      value={prop.value}
      disabled={sheet.running}
      aria-label={row.label}
      onChange={(value) => sheet.set(row.name, value)}
    />
  {:else if typeof prop.value === 'number'}
    <NumberBox
      value={prop.value}
      min={prop.minimum ?? undefined}
      max={prop.maximum ?? undefined}
      step={prop.step ?? undefined}
      suffix={row.unit || undefined}
      disabled={sheet.running}
      aria-label={row.label}
      class="w-full"
      onChange={(value) => sheet.set(row.name, value)}
    />
  {:else}
    <TextBox
      value={String(prop.value)}
      disabled={sheet.running}
      aria-label={row.label}
      class="w-full"
      onChange={(value) => sheet.set(row.name, value)}
    />
  {/if}
{/snippet}

<!-- The Position section of an axis: its control, and what it reads now at the heading's end. -->
{#snippet position(control: Snippet, reading?: Snippet)}
  <Section heading="Position" trailing={reading}>
    <div class="frame-tinted px-2.5 py-2">{@render control()}</div>
  </Section>
{/snippet}

{#snippet axisPosition(axis: LinearAxis)}
  {#if axis.limits && axis.position !== undefined}
    {@const [min, max] = axis.limits}
    {@const step = axis.prop<number>('position')?.step}
    {#snippet control()}
      <Ruler
        aria-label="{displayName(id)} position"
        value={target ?? axis.position}
        reading={axis.position}
        {min}
        {max}
        step={step ?? 1}
        disabled={sheet.running}
        onChange={(value) => {
          target = value;
          sheet.moveTo(value);
        }}
      />
    {/snippet}
    {#snippet reading()}
      <span class="text-sm tabular-nums">
        {text(axis.position, step)}
        <span class="text-fg-muted">{axis.positionUnit}</span>
      </span>
    {/snippet}
    {@render position(control, reading)}
  {/if}
{/snippet}

{#snippet slotsPosition(slots: DiscreteAxis)}
  {#if slots.labels.length > 0}
    {#snippet control()}
      {@const expected = sheet.session?.expectedPosition(id)}
      <Choice
        value={slots.position}
        expected={typeof expected === 'string' ? expected : null}
        options={slots.labels}
        disabled={sheet.running}
        aria-label="{displayName(id)} position"
        onChange={(label) => sheet.moveTo(label)}
      />
    {/snippet}
    {@render position(control)}
  {/if}
{/snippet}

{#snippet pinFacts(kind: string, direction: string)}
  <span class="justify-self-start rounded-sm bg-tint-hover px-1.5 text-sm whitespace-nowrap text-fg-muted"
    >{kind} {direction}</span
  >
{/snippet}

{#snippet kept(value: unknown)}
  {#if plain(value)}
    {text(value)}
  {:else}
    <ObjectView data={value} expandDepth={0} class="bg-transparent py-0 shadow-none" />
  {/if}
{/snippet}

<div>
  {#if sheet.rig}
    <div class="flex flex-col gap-3.5">
      <div class="flex items-baseline justify-between gap-3">
        <h1 class="min-w-0 truncate text-lg font-medium">{displayName(id)}</h1>
        {#if sheet.device?.interface}<span class="shrink-0 text-sm text-fg-muted"
            >{displayName(sheet.device.interface.kind)}</span
          >{/if}
      </div>

      <div class="grid grid-cols-[repeat(auto-fit,minmax(min(100%,30rem),1fr))] items-start gap-5">
        {#if sheet.device}
          <div class="flex min-w-0 flex-col gap-5">
            {#if axis}
              {@render axisPosition(axis)}
            {:else if slots}
              {@render slotsPosition(slots)}
            {/if}

            {#if sheet.settings.length > 0}
              {#snippet settingsHeading()}
                <span class={[SETTINGS, 'pr-2.5']}>
                  Settings
                  <span>Device</span>
                  {#snippet profileHeading()}Profile{/snippet}
                  {@render keep(sheet.settings, 'The profile, for all settings', profileHeading, '-my-1')}
                </span>
              {/snippet}
              <Section heading={settingsHeading}>
                <div class={[GRID, SETTINGS]}>
                  {#each sheet.settings as row (row.name)}
                    {@const value = sheet.inProfile(row) ? text(sheet.saved[row.name], row.prop?.step) : null}
                    <span class="truncate text-fg-muted">{row.label}</span>
                    <span class="flex min-w-0 justify-end">
                      {#if row.prop}{@render control(row, row.prop)}{/if}
                    </span>
                    {#snippet profileValue()}
                      {#if value === null}
                        <span class="text-fg-faint">-</span>
                      {:else}
                        <span class="truncate">{value} {row.unit}</span>
                      {/if}
                    {/snippet}
                    {@render keep(
                      [row],
                      `${row.label} in the profile: ${value === null ? 'none' : `${value} ${row.unit}`}`,
                      profileValue,
                      { 'text-accent-fg': sheet.differs(row) }
                    )}
                  {/each}
                </div>
              </Section>
            {/if}

            {#if sheet.readings.length > 0}
              <Section heading="Readings">
                <div class={[GRID, 'grid-cols-[minmax(0,1fr)_auto] gap-x-3']}>
                  {#each sheet.readings as row (row.name)}
                    {#if row.prop && !plain(row.prop.value)}
                      <details class="group col-span-full min-w-0">
                        <summary
                          class="flex min-h-ui-sm cursor-pointer list-none items-center gap-3 [&::-webkit-details-marker]:hidden"
                        >
                          <span class="min-w-0 flex-1 truncate text-fg-muted">{row.label}</span>
                          {#if row.unit}<span class="text-fg-muted">{row.unit}</span>{/if}
                          <span class="text-sm text-fg-faint tabular-nums">{size(row.prop.value)}</span>
                          <ChevronRight
                            class="size-3.5 text-fg-faint transition-transform group-open:rotate-90"
                            aria-hidden="true"
                          />
                        </summary>
                        <ObjectView data={row.prop.value} expandDepth={1} class="mt-1 mb-2" />
                      </details>
                    {:else}
                      <span class="truncate text-fg-muted">{row.label}</span>
                      <span class="truncate text-right tabular-nums">
                        {text(row.prop?.value, row.prop?.step)}
                        {#if row.prop?.value !== null && row.prop?.value !== undefined && row.unit}
                          <span class="text-fg-muted">{row.unit}</span>
                        {/if}
                      </span>
                    {/if}
                  {/each}
                </div>
              </Section>
            {/if}

            {#if sheet.pins.length > 0}
              <Section heading="Pins">
                <!-- Each pin it connects to, mirrored around a line that points from the out pin to the in pin. -->
                <div class={[GRID, 'grid-cols-[max-content_auto_minmax(1.5rem,1fr)_auto_max-content] gap-x-2']}>
                  {#each shownPins as pin (pin.name)}
                    {@const ends = sheet.instrument?.wires.ends(id, pin.name) ?? []}
                    {#each ends.length > 0 ? ends : [null] as end, index (end ? `${end.device}/${end.pin}` : '')}
                      {#if index === 0}
                        <span class="truncate pr-1 font-mono">{pin.name}</span>
                        {@render pinFacts(pin.kind, pin.direction)}
                      {:else}
                        <span class="col-span-2"></span>
                      {/if}
                      {#if end}
                        {@const far = farPin(end.device, end.pin, pin)}
                        <span
                          class={['flex items-center', pin.direction === 'in' && 'flex-row-reverse']}
                          aria-hidden="true"
                        >
                          <span class="h-px flex-1 bg-line"></span>
                          <span
                            class={[
                              'size-0 border-y-4 border-y-transparent',
                              pin.direction === 'in' ? 'border-r-6 border-r-line' : 'border-l-6 border-l-line'
                            ]}
                          ></span>
                        </span>
                        {@render pinFacts(far.kind, far.direction)}
                        <a
                          class="truncate pl-1 text-right font-mono hover:underline"
                          href={selection.href(
                            sheet.instrument?.name ?? '',
                            `devices/${encodeURIComponent(end.device)}`
                          )}>{end.device}/{end.pin}</a
                        >
                      {:else}
                        <span class="col-span-3"></span>
                      {/if}
                    {/each}
                  {/each}
                  {#if sheet.pins.length > shownPins.length}
                    <button
                      type="button"
                      class="col-span-full cursor-pointer text-left text-sm text-fg-muted hover:text-fg"
                      onclick={() => (allPins = true)}
                    >
                      ⋯ {sheet.pins.length - shownPins.length} more
                    </button>
                  {/if}
                </div>
              </Section>
            {/if}

            {#if sheet.commandGroups.length > 0}
              <Section heading="Commands">
                <div class="flex flex-col gap-3 frame-tinted p-2.5">
                  {#each sheet.commandGroups as group (group.label)}
                    <div class="flex flex-col gap-1.5">
                      <span class="text-sm text-fg-muted">{group.label}</span>
                      <div class="grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-2">
                        {#each group.commands as operation (operation.name)}
                          <Button variant="secondary" disabled={sheet.running} onclick={() => sheet.ask(operation)}>
                            {operation.label || displayName(operation.name)}
                          </Button>
                        {/each}
                      </div>
                    </div>
                  {/each}
                </div>
              </Section>
            {/if}
          </div>
        {/if}

        <div class="flex min-w-0 flex-col gap-5">
          {#if stage}
            {@const [axis, { specimen }] = stage}
            <Section heading="Stage">
              <div class="frame-tinted">
                <table class="table-lined table-fixed [&_td:first-child]:w-[10rem]">
                  <tbody>
                    <tr><td>Moves the specimen</td><td>{axis.toUpperCase()}</td></tr>
                    <tr>
                      <td>Specimen range</td>
                      <td>{specimen ? `${specimen[0]} to ${specimen[1]} µm` : 'Full travel'}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Section>
          {:else}
            <LightPathSection {id} />
          {/if}

          <Section heading="Profiles">
            {#if sheet.profiles.length > 0}
              <div class="frame-tinted">
                <table class="table-lined table-fixed">
                  <colgroup><col class="w-[10rem]" /><col class="w-[10rem]" /><col /></colgroup>
                  <tbody>
                    {#each sheet.profiles as profile (profile.id)}
                      {#each profile.kept as [setting, value], index (setting)}
                        <tr>
                          {#if index === 0}
                            <td rowspan={profile.kept.length}>
                              <a
                                class="font-medium hover:underline"
                                href={selection.href(
                                  sheet.instrument?.name ?? '',
                                  `profiles/${encodeURIComponent(profile.id)}`
                                )}>{profile.label}</a
                              >
                              {#if profile.id === sheet.session?.activeProfile}
                                <Check
                                  class="ml-1.5 inline size-3.5 align-[-0.15em] text-fg-muted"
                                  aria-label="Active"
                                />
                              {/if}
                            </td>
                          {/if}
                          <td>{setting}</td>
                          <td>{@render kept(value)}</td>
                        </tr>
                      {/each}
                    {/each}
                  </tbody>
                </table>
              </div>
            {:else}
              <p class="frame-tinted px-3 py-2 text-sm text-fg-muted">No profile uses it</p>
            {/if}
          </Section>

          <Section heading="Configuration">
            <div class="frame-tinted">
              <table class="table-lined table-fixed [&_td:first-child]:w-[10rem]">
                <tbody>
                  <tr><td>Driver</td><td class="font-mono wrap-anywhere">{sheet.rig.config.target}</td></tr>
                  <tr><td>Runs on</td><td>{sheet.rig.node ?? 'The station'}</td></tr>
                  {#if sheet.autosave}
                    <tr
                      ><td>Autosave</td><td
                        >{sheet.autosave === '*' ? 'Every setting' : sheet.autosave.map(displayName).join(', ')}</td
                      ></tr
                    >
                  {/if}
                  {#each sheet.init as [setting, value] (setting)}
                    <tr><td>{displayName(setting)}</td><td>{@render kept(value)}</td></tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </Section>
        </div>
      </div>
    </div>
  {/if}
</div>

{#snippet fields(list: OperationParam[], prefix: string, depth: number)}
  {#each list as param (param.name)}
    {@const key = prefix ? `${prefix}.${param.name}` : param.name}
    {@const label = displayName(param.name)}
    <span class={['text-sm text-fg-muted', param.fields && 'col-span-full']} style:padding-left="{depth * 0.9}rem">
      {label}
    </span>
    {#if param.fields}
      {@render fields(param.fields, key, depth + 1)}
    {:else if param.options}
      <Select
        value={sheet.argument(param, key) as string | number}
        options={param.options}
        aria-label={label}
        onChange={(value) => (sheet.values[key] = value)}
      />
    {:else if param.type === 'boolean'}
      <span class="flex justify-end">
        <Switch
          value={sheet.argument(param, key) as boolean}
          aria-label={label}
          onChange={(value) => (sheet.values[key] = value)}
        />
      </span>
    {:else if param.type === 'integer' || param.type === 'number'}
      <NumberBox
        value={sheet.argument(param, key) as number}
        step={param.type === 'integer' ? 1 : 0.1}
        aria-label={label}
        onChange={(value) => (sheet.values[key] = value)}
      />
    {:else}
      <TextBox
        live
        value={(param.type === 'other' ? (sheet.values[key] ?? '') : sheet.argument(param, key)) as string}
        aria-label={label}
        onChange={(value) => (sheet.values[key] = value)}
      />
    {/if}
  {/each}
{/snippet}

<Dialog.Root bind:open={() => sheet.command !== null, (open) => !open && !sheet.busy && (sheet.command = null)}>
  <Dialog.Content size="md" showCloseButton={false}>
    <Dialog.Header>
      <Dialog.Title>{sheet.command?.label || displayName(sheet.command?.name ?? '')}</Dialog.Title>
      {#if sheet.command?.desc}<Dialog.Description>{sheet.command.desc}</Dialog.Description>{/if}
    </Dialog.Header>
    {#if sheet.params.length > 0}
      <div
        class="relative grid max-h-[60dvh] grid-cols-[max-content_minmax(0,1fr)] items-center gap-x-4 gap-y-1.5 overflow-y-auto frame-tinted px-3 py-2.5"
      >
        {@render fields(sheet.params, '', 0)}
      </div>
    {/if}
    {#if sheet.result}
      <dl class="grid grid-cols-[max-content_minmax(0,1fr)] items-baseline gap-x-4 frame-tinted px-3 py-2.5">
        <dt class="text-sm text-fg-muted">Result</dt>
        <dd class="min-w-0 wrap-anywhere tabular-nums">{@render kept(sheet.result.value)}</dd>
      </dl>
    {/if}
    {#if sheet.failure}
      <p class="rounded-sm bg-danger-tint px-3 py-2 text-sm wrap-anywhere text-danger-fg" role="alert">
        {sheet.failure}
      </p>
    {/if}
    <Dialog.Footer>
      <Button variant="secondary" disabled={sheet.busy} onclick={() => (sheet.command = null)}>Close</Button>
      <Button disabled={sheet.busy || sheet.running} onclick={() => sheet.run()}>Run</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
