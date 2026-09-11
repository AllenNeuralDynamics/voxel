<script lang="ts">
  import { SvelteSet } from 'svelte/reactivity';

  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { wavelengthToColor } from '$lib/colors.svelte';
  import { ChevronDown, ChevronRight, InformationOutline } from '$lib/icons';
  import { resolveInstrumentView } from '$lib/instrument-view';
  import { Button, JsonView } from '$lib/kit';
  import { type DeviceHandle, getVoxelStation, type Instrument, type Prop } from '$lib/model';
  import { displayName, toastError } from '$lib/utils';

  import PageHeader from '../../../../../PageHeader.svelte';
  import ProfilePropertyRow from '../../ProfilePropertyRow.svelte';

  const app = getVoxelStation();
  const expandedDevices = new SvelteSet<string>();
  const stationId = $derived(page.params.stationId ?? '');
  const instrumentId = $derived(page.params.instrumentId ?? '');
  const routeParams = $derived({ stationId, instrumentId });
  const profileId = $derived(page.params.profileId ?? '');
  const activeInstrument = $derived(app.activeName === instrumentId ? app.instrument : null);
  const selected = $derived(
    instrumentId ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: instrumentId }) : null
  );
  const instrumentState = $derived(activeInstrument?.state ?? selected?.state);
  const hal = $derived(activeInstrument?.hal ?? selected?.config?.hal);
  const profile = $derived(instrumentState?.imaging.profiles[profileId ?? '']);
  // Only expose live operations when the profile being viewed is actually active.
  const instrument = $derived(activeInstrument?.activeProfileId === profileId ? activeInstrument : null);
  let activating = $state(false);
  const canActivate = $derived(
    activeInstrument && (activeInstrument.mode === 'idle' || activeInstrument.mode === 'preview')
  );

  async function activateProfile() {
    if (!activeInstrument || !profileId || !profile || instrument || !canActivate || activating) return;
    activating = true;
    try {
      await activeInstrument.setActiveProfile(profileId);
    } finally {
      activating = false;
    }
  }

  const configurationLinks = $derived(
    Object.fromEntries(
      (profile?.channels ?? []).map((channelId, index) => [
        `/channels/${index}`,
        resolve('/stations/[stationId]/instruments/[instrumentId]/channels/[channelId]', { ...routeParams, channelId })
      ])
    )
  );
  const channels = $derived(
    profile?.channels.map((id) => ({ id, config: instrumentState?.imaging.channels[id] })) ?? []
  );
  const generators = $derived(Object.entries(profile?.sync ?? {}));
  const waveformOutputGroups = $derived.by(() => {
    if (!instrument) return [];
    const channelDeviceIds = new SvelteSet<string>();
    for (const channel of instrument.activeChannels) {
      channelDeviceIds.add(channel.camera.id);
      channelDeviceIds.add(channel.laser.id);
      for (const filter of channel.filters) channelDeviceIds.add(filter.wheel.id);
      for (const device of channel.auxilliary) channelDeviceIds.add(device.id);
    }
    const stageDeviceIds = new SvelteSet(
      [instrument.hal.stage.x, instrument.hal.stage.y, instrument.hal.stage.z].filter(Boolean)
    );
    return generators
      .map(([generatorId, signals]) => ({
        generatorId,
        outputs: Object.keys(signals.waveforms).filter(
          (id) => !channelDeviceIds.has(id) && !stageDeviceIds.has(id) && !instrument.devices.has(id)
        )
      }))
      .filter((group) => group.outputs.length > 0);
  });
  const otherDevices = $derived.by(() => {
    if (!profile) return [];
    const channelDevices = new SvelteSet<string>();
    for (const { config } of channels) {
      if (!config) continue;
      const detection = hal?.detection[config.detection];
      const illumination = hal?.illumination[config.illumination];
      for (const id of [
        config.detection,
        config.illumination,
        ...Object.keys(config.filters),
        ...(detection?.filter_wheels ?? []),
        ...(detection?.aux_devices ?? []),
        ...(illumination?.aux_devices ?? [])
      ])
        channelDevices.add(id);
    }
    const references = new SvelteSet([
      ...Object.keys(profile.props),
      ...Object.keys(profile.rois),
      ...Object.keys(profile.setup),
      ...generators.flatMap(([, signals]) => Object.keys(signals.waveforms))
    ]);
    return [...references]
      .filter((id) => !channelDevices.has(id) && !Object.hasOwn(profile.sync, id))
      .sort((leftId, rightId) => {
        const left = instrument?.devices.get(leftId);
        const right = instrument?.devices.get(rightId);
        const leftAvailable = Boolean(left?.connected && !left.error);
        const rightAvailable = Boolean(right?.connected && !right.error);
        return Number(rightAvailable) - Number(leftAvailable);
      });
  });
  const numberFormat = new Intl.NumberFormat(undefined, { maximumSignificantDigits: 6 });
  const cardClass =
    'group flex min-w-0 flex-col gap-4 rounded-lg border border-border-faint/50 bg-elevated/60 p-3 transition-colors hover:border-border hover:bg-elevated focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focused';
  const gridClass = 'grid grid-cols-[repeat(auto-fit,minmax(min(100%,15rem),1fr))] gap-3';
  const profileActionClass = 'h-ui-xs w-20 rounded-md text-base';
</script>

{#snippet otherDeviceCard(instrument: Instrument, deviceId: string, device: DeviceHandle | undefined)}
  {@const expanded = expandedDevices.has(deviceId)}
  {@const pinnedNames = device?.interface?.type === 'continuous_axis' ? ['position'] : []}
  {@const pinnedProps = pinnedNames
    .map((name) => device?.getProp(name))
    .filter((prop): prop is Prop => prop?.access === 'rw')}
  {@const otherProps = [...(device?.props.values() ?? [])].filter(
    (prop) => prop.access === 'rw' && !pinnedNames.includes(prop.info.name)
  )}

  <section
    class="min-w-0 self-start rounded-lg border border-border-faint/50 bg-elevated/60 p-3"
    aria-label={displayName(deviceId)}
  >
    <button
      type="button"
      class="flex w-full items-center gap-2 text-left text-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focused enabled:cursor-pointer enabled:hover:text-fg-muted"
      disabled={!otherProps.length}
      aria-expanded={otherProps.length ? expanded : undefined}
      onclick={() => (expanded ? expandedDevices.delete(deviceId) : expandedDevices.add(deviceId))}
    >
      <span class="min-w-0 flex-1 text-base wrap-anywhere">{displayName(deviceId)}</span>
      {#if otherProps.length}
        {#if expanded}<ChevronDown class="size-4 shrink-0 text-fg-faint" aria-hidden="true" />
        {:else}<ChevronRight class="size-4 shrink-0 text-fg-faint" aria-hidden="true" />{/if}
      {/if}
    </button>

    {#if !device}
      <p class="mt-2 text-sm text-fg-muted">Device unavailable.</p>
    {:else}
      {#if device.error || !device.connected}
        <p class="mt-2 text-sm wrap-anywhere text-fg-muted">{device.error || 'Device disconnected.'}</p>
      {/if}
      {#if pinnedProps.length || (expanded && otherProps.length)}
        <div class="mt-3 space-y-3">
          {#each pinnedProps as prop (prop.info.name)}<ProfilePropertyRow {instrument} {device} {prop} compact />{/each}
          {#if expanded}
            {#each otherProps as prop (prop.info.name)}<ProfilePropertyRow
                {instrument}
                {device}
                {prop}
                compact
              />{/each}
          {/if}
        </div>
      {:else if !otherProps.length}
        <p class="mt-2 text-sm text-fg-muted">No editable properties available.</p>
      {/if}
    {/if}
  </section>
{/snippet}

<section class="flex h-full min-h-0 min-w-0 flex-col">
  <PageHeader items={[{ label: 'Profiles' }, { label: profile?.label || displayName(profileId ?? '') }]}>
    {#snippet trailing()}
      {#if profile && activeInstrument}
        {#if instrument && !activating}
          <span
            class={`inline-flex shrink-0 items-center justify-center border border-transparent bg-element-bg font-medium text-fg-muted ${profileActionClass}`}
            >Active</span
          >
        {:else}
          <Button
            variant="outline"
            size="xs"
            class={profileActionClass}
            loading={activating}
            disabled={!canActivate}
            title={canActivate ? 'Activate this profile' : 'Profiles can only be activated while idle or previewing'}
            onclick={() => toastError(activateProfile())}>Activate</Button
          >
        {/if}
      {/if}
    {/snippet}
  </PageHeader>

  {#if profile}
    <main class="min-h-0 flex-1 overflow-y-auto px-4 pb-5">
      <div class="space-y-6">
        <section aria-labelledby="channels-heading" class="space-y-2.5">
          <h2 id="channels-heading" class="flex items-baseline gap-2 text-base text-fg">
            Channels <span class="text-sm text-fg-faint">{channels.length}</span>
          </h2>
          <div class={gridClass}>
            {#each channels as channel (channel.id)}
              <a
                href={resolve('/stations/[stationId]/instruments/[instrumentId]/channels/[channelId]', {
                  ...routeParams,
                  channelId: channel.id
                })}
                class={cardClass}
              >
                <div class="flex items-center gap-2.5">
                  <span class="min-w-0 flex-1 text-base wrap-anywhere text-fg"
                    >{channel.config?.label || displayName(channel.id)}</span
                  >
                  {#if channel.config?.emission}<span class="shrink-0 text-sm text-fg-muted tabular-nums"
                      >{channel.config.emission} nm</span
                    >{/if}
                  <!-- The glyph ends at x=16 in a 24-wide viewBox; offset its empty right third. -->
                  <ChevronRight
                    class="size-4 shrink-0 translate-x-1/3 text-fg-faint"
                    style={channel.config?.emission
                      ? `color: ${wavelengthToColor(channel.config.emission)}`
                      : undefined}
                    aria-hidden="true"
                  />
                </div>
                {#if channel.config}
                  <dl class="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-3 gap-y-1.5">
                    <dt class="text-sm text-fg-muted">Detection</dt>
                    <dd class="text-right text-base wrap-anywhere text-fg">
                      {displayName(channel.config.detection)}
                    </dd>
                    <dt class="text-sm text-fg-muted">Illumination</dt>
                    <dd class="text-right text-base wrap-anywhere text-fg">
                      {displayName(channel.config.illumination)}
                    </dd>
                  </dl>
                {:else}<p class="text-sm text-fg-muted">Configuration unavailable</p>{/if}
              </a>
            {:else}
              <p class="rounded-lg border border-dashed border-border-faint/40 p-4 text-sm text-fg-muted">
                No channels assigned.
              </p>
            {/each}
          </div>
        </section>

        {#if activeInstrument && !instrument}
          <div class="flex max-w-3xl items-start gap-3 rounded-lg bg-element-bg/40 p-4" role="status">
            <InformationOutline class="mt-0.5 size-4 shrink-0 text-fg-muted" aria-hidden="true" />
            <div class="min-w-0 space-y-1">
              <p class="text-base wrap-anywhere text-fg">This profile is not active</p>
              <p class="text-sm wrap-anywhere text-fg-muted">
                You can inspect its configuration below. Activate this profile to access operating controls.
              </p>
            </div>
          </div>
        {/if}

        {#if instrument}
          <section aria-labelledby="sync-heading" class="space-y-2.5">
            <h2 id="sync-heading" class="flex items-baseline gap-2 text-base text-fg">
              Synchronization <span class="text-sm text-fg-faint">{generators.length}</span>
            </h2>
            <div class={gridClass}>
              {#each generators as [generatorId, signals] (generatorId)}
                <a
                  href={resolve(
                    '/stations/[stationId]/instruments/[instrumentId]/profiles/[profileId]/sync/[generatorId]',
                    { ...routeParams, profileId, generatorId }
                  )}
                  class={cardClass}
                >
                  <div class="flex items-center gap-2.5">
                    <span class="min-w-0 flex-1 text-base wrap-anywhere text-fg">{displayName(generatorId)}</span>
                    <ChevronRight class="size-4 shrink-0 text-fg-faint group-hover:text-fg" aria-hidden="true" />
                  </div>
                  <dl class="grid grid-cols-2 gap-3">
                    <div>
                      <dt class="mb-1 text-sm text-fg-muted">Outputs</dt>
                      <dd class="text-lg text-fg tabular-nums">{Object.keys(signals.waveforms).length}</dd>
                    </div>
                    <div>
                      <dt class="mb-1 text-sm text-fg-muted">Active duration</dt>
                      <dd class="text-lg text-fg tabular-nums">
                        {numberFormat.format(signals.duration * 1000)} <span class="text-sm text-fg-muted">ms</span>
                      </dd>
                    </div>
                  </dl>
                </a>
              {:else}
                <p class="rounded-lg border border-dashed border-border-faint/40 p-4 text-sm text-fg-muted">
                  No synchronization configured.
                </p>
              {/each}
            </div>
          </section>

          <section aria-labelledby="other-devices-heading" class="space-y-2.5">
            <h2 id="other-devices-heading" class="flex items-baseline gap-2 text-base text-fg">
              Other devices <span class="text-sm text-fg-faint">{otherDevices.length}</span>
            </h2>
            <div class="grid grid-cols-1 gap-3">
              {#each otherDevices as deviceId (deviceId)}
                {@render otherDeviceCard(instrument, deviceId, instrument.devices.get(deviceId))}
              {:else}
                <p class="rounded-lg border border-dashed border-border-faint/40 p-4 text-sm text-fg-muted">
                  No other devices referenced.
                </p>
              {/each}
            </div>
          </section>

          {#if generators.length > 0}
            <section aria-labelledby="tune-heading" class="space-y-2.5">
              <h2 id="tune-heading" class="text-base text-fg">Tune</h2>
              <div class="space-y-2">
                {#each waveformOutputGroups as group (group.generatorId)}
                  <div class="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-3 text-base">
                    <span class="wrap-anywhere text-fg-muted">{displayName(group.generatorId)}</span>
                    <span class="wrap-anywhere text-fg">{group.outputs.map(displayName).join(', ')}</span>
                  </div>
                {:else}
                  <p class="text-sm text-fg-muted">No additional waveform outputs.</p>
                {/each}
              </div>
            </section>
          {/if}
        {/if}
        <section
          class="min-w-0 space-y-3 rounded-lg border border-border-faint/50 p-3"
          aria-labelledby="profile-configuration-heading"
        >
          <h2 id="profile-configuration-heading" class="text-sm text-fg-muted">Profile configuration</h2>
          <!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard users need to scroll wide configuration values.) -->
          <div class="overflow-x-auto" role="region" aria-label="Profile configuration" tabindex="0">
            <JsonView data={profile} expandDepth={1} links={configurationLinks} />
          </div>
        </section>
      </div>
    </main>

    {#if instrument}
      <footer class="flex h-10 shrink-0 items-center justify-end gap-1.5 border-t border-border px-4">
        <Button variant="outline" size="xs" onclick={() => toastError(instrument.applySettings())}>Apply Saved</Button>
        <Button variant="outline" size="xs" onclick={() => toastError(instrument.saveSettings())}>Save Current</Button>
      </footer>
    {/if}
  {:else}
    <p class="p-4 text-fg-muted">Open an instrument and select a profile to view its overview.</p>
  {/if}
</section>
