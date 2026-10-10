<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { wavelengthToColor } from '$lib/colors.svelte';
  import { buildDeviceTopology, groupDevicesForNavigation } from '$lib/device-topology';
  import CameraControlCard from '$lib/devices/CameraControlCard2.svelte';
  import LaserControlCard from '$lib/devices/LaserControlCard2.svelte';
  import { ChevronRight } from '$lib/icons';
  import { resolveInstrumentView } from '$lib/instrument-view';
  import { getVoxelStation } from '$lib/model';
  import PageHeader from '$lib/PageHeader.svelte';
  import { displayName } from '$lib/utils';

  import RoutingControls from '../routing/RoutingControls.svelte';
  import FilterWheels from './FilterWheels.svelte';

  const app = getVoxelStation();
  const instrumentId = $derived(page.params.instrumentId ?? '');
  const routeParams = $derived({ stationId: page.params.stationId ?? '', instrumentId });
  const selected = $derived(resolveInstrumentView(app.discovery, { kind: 'instrument', name: instrumentId }));
  const instrument = $derived(app.activeName === instrumentId ? app.instrument : null);
  const hal = $derived(instrument?.hal ?? selected?.config?.hal);
  const state = $derived(instrument?.state ?? selected?.state);
  const groups = $derived(hal && state ? groupDevicesForNavigation(buildDeviceTopology(hal, state.imaging)) : []);
  const hasRouting = $derived(Boolean(instrument?.routingDimensions.size));
  const hasWheels = $derived(Boolean(instrument?.filterWheels.length));

  function devicePath(deviceId: string) {
    return resolve('/stations/[stationId]/instruments/[instrumentId]/devices/[deviceId]', { ...routeParams, deviceId });
  }
  function channelLabel(channelId: string) {
    return state?.imaging.channels[channelId]?.label || displayName(channelId);
  }
</script>

<div class="flex h-full min-h-0 min-w-0 flex-col bg-canvas">
  <PageHeader items={[{ label: displayName(instrumentId) }]} />
  <div class="min-h-0 flex-1 overflow-y-auto">
    {#if hal && state}
      <div class="max-w-4xl space-y-4 px-4 pb-4">
        {#if instrument && hasRouting}
          <section id="routing" class="scroll-mt-3 space-y-2">
            <h2 class="text-base text-fg">Routing</h2>
            <RoutingControls {instrument} />
          </section>
        {/if}
        {#if instrument && hasWheels}<FilterWheels {instrument} />{/if}

        {#if instrument}
          <section aria-labelledby="cameras-heading" class="space-y-2.5">
            <h2 id="cameras-heading" class="flex items-baseline gap-2 text-base text-fg">
              Cameras <span class="text-sm text-fg-faint">{instrument.cameras.size}</span>
            </h2>
            <div class="grid grid-cols-1 gap-3">
              {#each instrument.cameras.values() as camera (camera.id)}
                <CameraControlCard {camera} {instrument} />
              {:else}
                <p class="text-sm text-fg-muted">No cameras available.</p>
              {/each}
            </div>
          </section>

          <section aria-labelledby="lasers-heading" class="space-y-2.5">
            <h2 id="lasers-heading" class="flex items-baseline gap-2 text-base text-fg">
              Lasers <span class="text-sm text-fg-faint">{instrument.lasers.size}</span>
            </h2>
            <div class="grid grid-cols-1 gap-3">
              {#each instrument.lasers.values() as laser (laser.id)}
                <LaserControlCard {laser} {instrument} />
              {:else}
                <p class="text-sm text-fg-muted">No lasers available.</p>
              {/each}
            </div>
          </section>
        {/if}

        <section id="profiles" class="scroll-mt-3 overflow-hidden rounded-lg border border-line-muted">
          <h2 class="px-3 pt-3 pb-1 text-base text-fg">Profiles</h2>
          <div class="divide-y divide-line-faint">
            {#each Object.entries(state.imaging.profiles) as [profileId, profile] (profileId)}
              <a
                class="flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-element-hover"
                href={resolve('/stations/[stationId]/instruments/[instrumentId]/profiles/[profileId]/overview', {
                  ...routeParams,
                  profileId
                })}
              >
                <div class="min-w-0 flex-1">
                  <div class="truncate text-fg">{profile.label || displayName(profileId)}</div>
                  <div class="truncate text-sm text-fg-muted" title={profile.channels.map(channelLabel).join(' · ')}>
                    {profile.channels.map(channelLabel).join(' · ') || 'No channels'}
                  </div>
                </div>
                {#if instrument?.activeProfileId === profileId}<span class="text-sm text-fg-muted">Active</span>{/if}
                <ChevronRight class="size-3.5 shrink-0 text-fg-faint" />
              </a>
            {:else}<p class="px-3 py-2 text-sm text-fg-muted">No profiles.</p>{/each}
          </div>
        </section>

        <section id="channels" class="scroll-mt-3 overflow-hidden rounded-lg border border-line-muted">
          <h2 class="px-3 pt-3 pb-1 text-base text-fg">Channels</h2>
          <div class="divide-y divide-line-faint">
            {#each Object.entries(state.imaging.channels) as [channelId, channel] (channelId)}
              <div class="px-3 py-2.5">
                <a
                  class="flex items-center gap-2 text-fg hover:text-fg-accent"
                  href={resolve('/stations/[stationId]/instruments/[instrumentId]/channels/[channelId]', {
                    ...routeParams,
                    channelId
                  })}
                >
                  {#if channel.emission != null}<span
                      class="size-1.5 shrink-0 rounded-full"
                      style:background-color={wavelengthToColor(channel.emission)}
                    ></span>{/if}
                  <span class="min-w-0 flex-1 truncate">{channelLabel(channelId)}</span>
                  <ChevronRight class="size-3.5 shrink-0 text-fg-faint" />
                </a>
                <div class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-sm text-fg-muted">
                  <a href={devicePath(channel.illumination)} class="hover:text-fg" title="Laser"
                    >{displayName(channel.illumination)}</a
                  >
                  <a href={devicePath(channel.detection)} class="hover:text-fg" title="Camera"
                    >{displayName(channel.detection)}</a
                  >
                </div>
              </div>
            {:else}<p class="px-3 py-2 text-sm text-fg-muted">No channels.</p>{/each}
          </div>
        </section>

        <section id="devices" class="scroll-mt-3 overflow-hidden rounded-lg border border-line-muted">
          <h2 class="px-3 pt-3 pb-1 text-base text-fg">Devices</h2>
          {#each groups as group (group.id)}
            <div class="border-t border-line-faint px-3 py-2">
              <h3 class="mb-1 text-sm text-fg-muted">{group.label}</h3>
              {#each group.deviceIds as deviceId (deviceId)}
                {@const device = instrument?.devices.get(deviceId)}
                <a
                  class="flex items-center gap-2 rounded-sm py-1.5 text-fg transition-colors hover:bg-element-hover"
                  href={devicePath(deviceId)}
                >
                  <span class="min-w-0 flex-1 truncate">{displayName(deviceId)}</span>
                  {#if device?.error || (device && !device.connected)}
                    <span class="text-xs text-warning" title={device.error || 'Disconnected'}
                      >{device.error ? 'Error' : 'Offline'}</span
                    >
                  {/if}
                  <ChevronRight class="size-3.5 shrink-0 text-fg-faint" />
                </a>
              {/each}
            </div>
          {/each}
        </section>

        <section id="configuration" class="scroll-mt-3 overflow-hidden rounded-lg border border-line-muted">
          <h2 class="px-3 pt-3 pb-1 text-base text-fg">Configuration</h2>
          <a
            class="flex items-center justify-between px-3 py-2.5 text-fg hover:bg-element-hover"
            href={resolve('/stations/[stationId]/instruments/[instrumentId]/presets', routeParams)}
            >Presets<ChevronRight class="size-3.5 text-fg-faint" /></a
          >
          <a
            class="flex items-center justify-between border-t border-line-faint px-3 py-2.5 text-fg hover:bg-element-hover"
            href={resolve('/stations/[stationId]/instruments/[instrumentId]', routeParams)}
            >Configuration & defaults<ChevronRight class="size-3.5 text-fg-faint" /></a
          >
        </section>
      </div>
    {:else}<p class="px-4 text-sm text-fg-muted">Instrument configuration unavailable.</p>{/if}
  </div>
</div>
