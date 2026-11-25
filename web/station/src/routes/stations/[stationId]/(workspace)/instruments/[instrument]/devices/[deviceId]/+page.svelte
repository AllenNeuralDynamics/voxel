<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { ClassValue } from 'svelte/elements';

  import { page } from '$app/state';
  import { getInstrumentSelection, useAppBar } from '$lib/context.svelte';
  import { SpimSession } from '$lib/core/spim.svelte';
  import type { OperationInfo, OperationParam, PropValue } from '$lib/core/types';
  import {
    Button,
    Dialog,
    NumberBox,
    ObjectDiff,
    ObjectView,
    Popover,
    RadioBar,
    Section,
    Select,
    Switch,
    TextBox
  } from '@voxel/kit';
  import { errorMessage, reportFailure } from '@voxel/kit/failures';
  import { displayName } from '@voxel/kit/format';
  import { Check, ChevronRight, X } from '@voxel/kit/icons';

  const selection = getInstrumentSelection();
  const name = $derived(page.params.instrument ?? '');
  const id = $derived(page.params.deviceId ?? '');
  const instrument = $derived(selection.instrument);
  const session = $derived(selection.session);
  const rig = $derived(instrument?.deviceConfigs[id]);
  const device = $derived(session?.device(id));
  const running = $derived(session instanceof SpimSession && session.acquisition !== undefined);

  interface Row {
    name: string;
    label: string;
    unit: string;
    prop: PropValue | undefined;
  }

  const rows = $derived(
    Object.values(device?.interface?.props ?? {}).map((info): Row & { settable: boolean } => ({
      name: info.name,
      label: info.label || displayName(info.name),
      unit: info.units,
      prop: device?.prop(info.name),
      settable: info.access === 'rw'
    }))
  );
  // Lists and maps have no control.
  const settings = $derived(
    rows.filter((row) => row.settable && row.prop && plain(row.prop.value) && row.prop.value !== null)
  );
  const readings = $derived(rows.filter((row) => !settings.includes(row) && row.name !== 'pins'));
  const pins = $derived((device?.prop('pins')?.value ?? []) as { name: string; direction: string; kind: string }[]);
  const PINS_SHOWN = 8;
  let allPins = $state(false);
  const shownPins = $derived(allPins ? pins : pins.slice(0, PINS_SHOWN));
  const commands = $derived(Object.values(device?.interface?.operations ?? {}));
  const commandGroups = $derived(
    [
      { label: 'Queries', commands: commands.filter((operation) => operation.intent === 'query') },
      { label: 'Actions', commands: commands.filter((operation) => operation.intent !== 'query') }
    ].filter((group) => group.commands.length > 0)
  );
  let command = $state<OperationInfo | null>(null);
  const params = $derived(command && device ? device.params(command.name) : []);
  let values = $state<Record<string, unknown>>({});
  let busy = $state(false);
  let failure = $state<string | null>(null);
  let result = $state<{ value: unknown } | null>(null);

  const saved = $derived(session?.saved(id) ?? {});
  const differing = $derived(new Set(session?.differing(id) ?? []));
  const inProfile = (row: Row): boolean => row.name in saved;
  // A kept setting can leave the profile unless every write saves it again.
  const removable = (row: Row): boolean => inProfile(row) && !session?.autosaved(id, row.name);

  const profiles = $derived(
    (instrument?.state.profileIds ?? []).flatMap((profileId) => {
      const profile = instrument?.state.profile(profileId);
      if (!profile) return [];
      const channels = Object.entries(profile.channels)
        .filter(([, cameras]) => Object.entries(cameras).some(([camera, light]) => camera === id || light === id))
        .map(([channel]) => displayName(channel));
      const power = profile.power[id];
      const kept: [setting: string, value: unknown][] = [
        ...(channels.length > 0 ? ([['Channel', channels.join(', ')]] as [string, unknown][]) : []),
        ...(power
          ? ([
              ['Power, full', power.full],
              ['Power, dim', power.dim]
            ] as [string, unknown][])
          : []),
        ...(id in profile.positions ? ([['Position', profile.positions[id]]] as [string, unknown][]) : []),
        ...Object.entries(profile.props[id] ?? {}).map(([prop, value]): [string, unknown] => [displayName(prop), value])
      ];
      return kept.length > 0 ? [{ id: profileId, label: profile.label || displayName(profileId), kept }] : [];
    })
  );

  const autosave = $derived(instrument?.config?.autosave[id]);
  const init = $derived(Object.entries(rig?.config.init ?? {}));

  function plain(value: unknown): boolean {
    return ObjectDiff.parts(value) === undefined;
  }

  /** A number has the decimals of `step`, or at most 4. */
  function text(value: unknown, step?: number | null): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'boolean') return value ? 'On' : 'Off';
    if (typeof value !== 'number') return String(value);
    const decimals = step ? (String(step).split('.')[1]?.length ?? 0) : 4;
    return String(Number(value.toFixed(decimals)));
  }

  function size(value: unknown): number {
    return Object.keys(ObjectDiff.parts(value) ?? {}).length;
  }

  function set(property: string, value: unknown): void {
    if (device) reportFailure(device.set({ [property]: value }));
  }

  function ask(operation: OperationInfo): void {
    command = operation;
    values = {};
    failure = null;
    result = null;
  }

  /** `key` is the dotted path from the command to the argument. */
  function argument(param: OperationParam, key: string): unknown {
    if (values[key] !== undefined) return values[key];
    if (param.default !== undefined && param.default !== null) return param.default;
    if (param.options) return param.options[0];
    if (param.type === 'boolean') return false;
    return param.type === 'integer' || param.type === 'number' ? 0 : '';
  }

  /** Undefined leaves an untyped optional argument out, so the device uses its default. */
  function sent(param: OperationParam, key: string): unknown {
    if (param.fields) {
      const parts = param.fields.map((field) => [field.name, sent(field, `${key}.${field.name}`)]);
      const typed = Object.keys(values).some((other) => other.startsWith(`${key}.`));
      return param.required || typed ? Object.fromEntries(parts.filter(([, value]) => value !== undefined)) : undefined;
    }
    if (param.type === 'other') return values[key] ? JSON.parse(values[key] as string) : undefined;
    return param.required || values[key] !== undefined ? argument(param, key) : undefined;
  }

  /** The dialog stays open to show a value or a failure. */
  async function run(): Promise<void> {
    if (!command || !device || busy) return;
    busy = true;
    try {
      const args = Object.fromEntries(
        params.map((param) => [param.name, sent(param, param.name)]).filter(([, value]) => value !== undefined)
      );
      const value = await device.run(command.name, args);
      failure = null;
      if (value === null || value === undefined) command = null;
      else result = { value };
    } catch (error) {
      failure = errorMessage(error);
      result = null;
      // The dialog shows the failure, so the Issues list keeps it without a toast.
      reportFailure(error, { toast: false });
    } finally {
      busy = false;
    }
  }

  useAppBar(() => ({
    crumbs: [{ label: 'Devices', href: selection.href(name, 'devices') }, { label: displayName(id) }]
  }));

  const SETTINGS = 'grid grid-cols-[minmax(0,1fr)_8.5rem_6rem] items-center gap-x-2';
  const GRID = 'grid auto-rows-[minmax(var(--ui-sm),auto)] items-center gap-y-1.5 rounded-md bg-tint px-2.5 py-2';
  const TABLE =
    'w-full border-collapse text-sm tabular-nums [&_td]:border-t [&_td]:border-line-faint [&_td]:px-3 [&_td]:py-1.5 [&_td]:align-top';
  const ITEM =
    'flex h-ui-sm w-full cursor-pointer items-center justify-between gap-3 rounded-sm px-2 text-left hover:bg-element-hover focus-visible:bg-element-hover focus-visible:outline-none';
  const CELL =
    'group/cell flex h-ui-xs w-full cursor-pointer items-center justify-end gap-2 rounded-sm px-1.5 text-right tabular-nums hover:bg-element-hover focus-visible:bg-element-hover focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50';
</script>

{#snippet keep(list: Row[], label: string, trigger: Snippet, triggerClass: ClassValue)}
  {@const names = list.map((row) => row.name)}
  {@const removing = list.filter(removable)}
  <Popover.Root>
    <Popover.Trigger class={triggerClass} aria-label={label} disabled={running}>
      {@render trigger()}
    </Popover.Trigger>
    <Popover.Content class="flex w-44 flex-col gap-px p-1 text-sm" side="bottom" align="end" sideOffset={4}>
      <button type="button" class={ITEM} onclick={() => reportFailure(session?.saveToProfile(id, names))}>
        Save to profile<Check class="size-3.5" aria-hidden="true" />
      </button>
      {#if list.every(inProfile)}
        <button type="button" class={ITEM} onclick={() => reportFailure(session?.restoreFromProfile(id, names))}>
          Restore from profile<Check class="size-3.5" aria-hidden="true" />
        </button>
      {/if}
      {#if removing.length > 0}
        <button
          type="button"
          class={ITEM}
          onclick={() =>
            reportFailure(
              session?.removeFromProfile(
                id,
                removing.map((row) => row.name)
              )
            )}
        >
          Remove from profile<X class="size-3.5" aria-hidden="true" />
        </button>
      {/if}
    </Popover.Content>
  </Popover.Root>
{/snippet}

{#snippet control(row: Row, prop: PropValue)}
  {#if prop.options && prop.options.length <= 4}
    <RadioBar
      value={prop.value as string}
      options={prop.options as string[]}
      disabled={running}
      aria-label={row.label}
      class="w-full"
      onChange={(value) => set(row.name, value)}
    />
  {:else if prop.options}
    <Select
      value={prop.value as string}
      options={prop.options as string[]}
      disabled={running}
      aria-label={row.label}
      class="w-full"
      onChange={(value) => set(row.name, value)}
    />
  {:else if typeof prop.value === 'boolean'}
    <Switch value={prop.value} disabled={running} aria-label={row.label} onChange={(value) => set(row.name, value)} />
  {:else if typeof prop.value === 'number'}
    <NumberBox
      value={prop.value}
      min={prop.minimum ?? undefined}
      max={prop.maximum ?? undefined}
      step={prop.step ?? undefined}
      suffix={row.unit || undefined}
      disabled={running}
      aria-label={row.label}
      class="w-full"
      onChange={(value) => set(row.name, value)}
    />
  {:else}
    <TextBox
      value={String(prop.value)}
      disabled={running}
      aria-label={row.label}
      class="w-full"
      onChange={(value) => set(row.name, value)}
    />
  {/if}
{/snippet}

{#snippet kept(value: unknown)}
  {#if plain(value)}
    {text(value)}
  {:else}
    <ObjectView data={value} expandDepth={0} class="bg-transparent py-0 shadow-none" />
  {/if}
{/snippet}

<div class="@container h-full page-body pt-4">
  {#if rig}
    <div class="flex flex-col gap-3.5">
      <div class="flex items-baseline justify-between gap-3">
        <h1 class="min-w-0 truncate text-lg font-medium">{displayName(id)}</h1>
        {#if device?.interface}<span class="shrink-0 text-sm text-fg-muted">{displayName(device.interface.kind)}</span
          >{/if}
      </div>

      <div class="grid grid-cols-[minmax(0,1fr)] items-start gap-5 @[60rem]:grid-cols-2">
        {#if device}
          <div class="flex min-w-0 flex-col gap-5">
            {#if settings.length > 0}
              {#snippet settingsHeading()}
                <span class={[SETTINGS, 'px-2.5']}>
                  Settings
                  <span>Device</span>
                  {#snippet profileHeading()}Profile{/snippet}
                  {@render keep(settings, 'The profile, for all settings', profileHeading, [CELL, '-my-1'])}
                </span>
              {/snippet}
              <Section heading={settingsHeading}>
                <div class={[GRID, SETTINGS]}>
                  {#each settings as row (row.name)}
                    {@const value = inProfile(row) ? text(saved[row.name], row.prop?.step) : null}
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
                      [CELL, differing.has(row.name) && 'text-accent-fg']
                    )}
                  {/each}
                </div>
              </Section>
            {/if}

            {#if readings.length > 0}
              <Section heading="Readings">
                <div class={[GRID, 'grid-cols-[minmax(0,1fr)_auto] gap-x-3']}>
                  {#each readings as row (row.name)}
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

            {#if pins.length > 0}
              <Section heading="Pins">
                <div class={[GRID, 'grid-cols-[minmax(0,1fr)_auto_auto] gap-x-5']}>
                  {#each shownPins as pin (pin.name)}
                    <span class="truncate font-mono">{pin.name}</span>
                    <span class="text-fg-muted">{pin.direction}</span>
                    <span class="text-fg-muted">{pin.kind}</span>
                  {/each}
                  {#if pins.length > shownPins.length}
                    <button
                      type="button"
                      class="col-span-full cursor-pointer text-left text-sm text-fg-muted hover:text-fg"
                      onclick={() => (allPins = true)}
                    >
                      ⋯ {pins.length - shownPins.length} more
                    </button>
                  {/if}
                </div>
              </Section>
            {/if}

            {#if commands.length > 0}
              <Section heading="Commands">
                <div class="flex flex-col gap-3 rounded-md bg-tint p-2.5">
                  {#each commandGroups as group (group.label)}
                    <div class="flex flex-col gap-1.5">
                      <span class="text-sm text-fg-muted">{group.label}</span>
                      <div class="grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-2">
                        {#each group.commands as operation (operation.name)}
                          <Button variant="secondary" disabled={running} onclick={() => ask(operation)}>
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
          <Section heading="Profiles">
            {#if profiles.length > 0}
              <div class="rounded-md bg-tint">
                <table class={TABLE}>
                  <tbody class="[&_tr:first-child_td]:border-t-0">
                    {#each profiles as profile (profile.id)}
                      {#each profile.kept as [setting, value], index (setting)}
                        <tr>
                          {#if index === 0}
                            <td class="whitespace-nowrap" rowspan={profile.kept.length}>
                              <a
                                class="font-medium hover:underline"
                                href={selection.href(name, `profiles/${encodeURIComponent(profile.id)}`)}
                                >{profile.label}</a
                              >
                              {#if profile.id === session?.activeProfile}
                                <span class="ml-1.5 text-fg-muted">Active</span>
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
              <p class="rounded-md bg-tint px-3 py-2 text-sm text-fg-muted">No profile uses it</p>
            {/if}
          </Section>

          <Section heading="Configuration">
            <div class="rounded-md bg-tint">
              <table class={[TABLE, '[&_td:first-child]:w-[10rem]']}>
                <tbody class="[&_tr:first-child_td]:border-t-0">
                  <tr><td>Driver</td><td class="font-mono wrap-anywhere">{rig.config.target}</td></tr>
                  <tr><td>Runs on</td><td>{rig.node ?? 'The station'}</td></tr>
                  {#if autosave}
                    <tr
                      ><td>Autosave</td><td
                        >{autosave === '*' ? 'Every setting' : autosave.map(displayName).join(', ')}</td
                      ></tr
                    >
                  {/if}
                  {#each init as [setting, value] (setting)}
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
        value={argument(param, key) as string | number}
        options={param.options}
        aria-label={label}
        onChange={(value) => (values[key] = value)}
      />
    {:else if param.type === 'boolean'}
      <span class="flex justify-end">
        <Switch
          value={argument(param, key) as boolean}
          aria-label={label}
          onChange={(value) => (values[key] = value)}
        />
      </span>
    {:else if param.type === 'integer' || param.type === 'number'}
      <NumberBox
        value={argument(param, key) as number}
        step={param.type === 'integer' ? 1 : 0.1}
        aria-label={label}
        onChange={(value) => (values[key] = value)}
      />
    {:else}
      <TextBox
        live
        value={(param.type === 'other' ? (values[key] ?? '') : argument(param, key)) as string}
        aria-label={label}
        onChange={(value) => (values[key] = value)}
      />
    {/if}
  {/each}
{/snippet}

<Dialog.Root bind:open={() => command !== null, (open) => !open && !busy && (command = null)}>
  <Dialog.Content size="md" showCloseButton={false}>
    <Dialog.Header>
      <Dialog.Title>{command?.label || displayName(command?.name ?? '')}</Dialog.Title>
      {#if command?.desc}<Dialog.Description>{command.desc}</Dialog.Description>{/if}
    </Dialog.Header>
    {#if params.length > 0}
      <div
        class="relative grid max-h-[60dvh] grid-cols-[max-content_minmax(0,1fr)] items-center gap-x-4 gap-y-1.5 overflow-y-auto rounded-md bg-tint px-3 py-2.5"
      >
        {@render fields(params, '', 0)}
      </div>
    {/if}
    {#if result}
      <dl class="grid grid-cols-[max-content_minmax(0,1fr)] items-baseline gap-x-4 rounded-md bg-tint px-3 py-2.5">
        <dt class="text-sm text-fg-muted">Result</dt>
        <dd class="min-w-0 wrap-anywhere tabular-nums">{@render kept(result.value)}</dd>
      </dl>
    {/if}
    {#if failure}
      <p class="rounded-sm bg-danger-tint px-3 py-2 text-sm wrap-anywhere text-danger-fg" role="alert">{failure}</p>
    {/if}
    <Dialog.Footer>
      <Button variant="secondary" disabled={busy} onclick={() => (command = null)}>Close</Button>
      <Button disabled={busy || running} onclick={run}>Run</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
