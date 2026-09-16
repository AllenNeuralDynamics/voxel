<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import type { ResolvedPathname } from '$app/types';
  import { buildDeviceTopology, groupDevicesForNavigation } from '$lib/device-topology';
  import { resolveInstrumentView } from '$lib/instrument-view';
  import { Sidebar } from '$lib/kit';
  import { getVoxelStation } from '$lib/model';
  import { displayName } from '$lib/utils';

  interface NavigationItem {
    label: string;
    href: ResolvedPathname;
    includeChildren?: boolean;
    inActiveProfile?: boolean;
  }

  let { instrumentId }: { instrumentId?: string } = $props();

  const app = getVoxelStation();
  const stationId = $derived(page.params.stationId ?? '');
  const routeParams = $derived({ stationId, instrumentId: instrumentId ?? '' });
  const selected = $derived(
    instrumentId ? resolveInstrumentView(app.discovery, { kind: 'instrument', name: instrumentId }) : null
  );
  const activeInstrument = $derived(instrumentId && app.activeName === instrumentId ? app.instrument : null);
  const hal = $derived(activeInstrument?.hal ?? selected?.config?.hal ?? null);
  const instrumentState = $derived(activeInstrument?.state ?? selected?.state ?? null);
  const topology = $derived(hal && instrumentState ? buildDeviceTopology(hal, instrumentState.imaging) : null);
  const deviceId = $derived(page.params.deviceId);
  const deviceGroups = $derived(topology ? groupDevicesForNavigation(topology) : []);
  const profileId = $derived(activeInstrument?.activeProfileId ?? '');
  const profiles = $derived(Object.entries(instrumentState?.imaging.profiles ?? {}));
  const instrumentChannels = $derived<NavigationItem[]>(
    Object.entries(instrumentState?.imaging.channels ?? {}).map(([channelId, channel]) => ({
      label: channel.label || displayName(channelId),
      href: resolve('/stations/[stationId]/instruments/[instrumentId]/channels/[channelId]', {
        ...routeParams,
        channelId
      }),
      inActiveProfile: activeInstrument?.activeProfile?.channels.includes(channelId) ?? false
    }))
  );
  const generatorNavigation = $derived<NavigationItem[]>(
    Object.keys(activeInstrument?.activeProfile?.sync ?? {}).map((generatorId) => ({
      label: displayName(generatorId),
      href: resolve('/stations/[stationId]/instruments/[instrumentId]/profiles/[profileId]/sync/[generatorId]', {
        ...routeParams,
        profileId,
        generatorId
      })
    }))
  );
  const acquisitionLink = $derived<NavigationItem>({
    label: 'Acquisitions',
    href: resolve('/stations/[stationId]/instruments/[instrumentId]/acquisitions', routeParams),
    includeChildren: true
  });

  function devicePath(targetId: string) {
    return resolve('/stations/[stationId]/instruments/[instrumentId]/devices/[deviceId]', {
      ...routeParams,
      deviceId: targetId
    });
  }

  function deviceIssue(targetId: string): { label: string; class: string } | null {
    const device = activeInstrument?.devices.get(targetId);
    if (!device) return null;
    if (device.error) return { label: device.error, class: 'bg-danger' };
    if (!device.connected) return { label: 'Disconnected', class: 'bg-warning' };
    return null;
  }
</script>

{#snippet navigationItem(item: NavigationItem)}
  {@const current = page.url.pathname === item.href}
  <Sidebar.MenuItem>
    <Sidebar.MenuButton
      isActive={current || (item.includeChildren === true && page.url.pathname.startsWith(`${item.href}/`))}
    >
      {#snippet child({ props })}
        <a {...props} href={item.href} aria-current={current ? 'page' : undefined}>
          <span>{item.label}</span>
          {#if item.inActiveProfile}
            <span class="ml-auto size-1.5 shrink-0 rounded-full bg-success" title="In active profile" aria-hidden="true"
            ></span>
            <span class="sr-only">In active profile</span>
          {/if}
        </a>
      {/snippet}
    </Sidebar.MenuButton>
  </Sidebar.MenuItem>
{/snippet}

{#if instrumentId}
  <Sidebar.Menu class="px-2 py-1">
    {@render navigationItem({
      label: 'Instrument',
      href: resolve('/stations/[stationId]/instruments/[instrumentId]', routeParams)
    })}
    {@render navigationItem(acquisitionLink)}
    {#if selected}
      {@render navigationItem({
        label: 'Presets',
        href: resolve('/stations/[stationId]/instruments/[instrumentId]/presets', routeParams),
        includeChildren: true
      })}
    {/if}
    {@render navigationItem({
      label: 'Routing',
      href: resolve('/stations/[stationId]/instruments/[instrumentId]/routing', routeParams)
    })}
    {#if activeInstrument}
      {@render navigationItem({
        label: 'Plan',
        href: resolve('/stations/[stationId]/instruments/[instrumentId]/plan', routeParams),
        includeChildren: true
      })}
    {/if}
  </Sidebar.Menu>
{/if}

{#if instrumentId && profiles.length}
  <Sidebar.Group class="py-2">
    <Sidebar.GroupLabel>Profiles</Sidebar.GroupLabel>
    <Sidebar.Menu>
      {#each profiles as [targetProfileId, profile] (targetProfileId)}
        {@const href = resolve('/stations/[stationId]/instruments/[instrumentId]/profiles/[profileId]/overview', {
          ...routeParams,
          profileId: targetProfileId
        })}
        {@const current = page.url.pathname === href}
        {@const label = profile.label || displayName(targetProfileId)}
        <Sidebar.MenuItem>
          <Sidebar.MenuButton isActive={page.params.profileId === targetProfileId} title={label}>
            {#snippet child({ props })}
              <a {...props} {href} aria-current={current ? 'page' : undefined}>
                <span class="min-w-0 flex-1 truncate">{label}</span>
                {#if profileId === targetProfileId}
                  <span
                    class="ml-auto size-1.5 shrink-0 rounded-full bg-success"
                    title="Active profile"
                    aria-hidden="true"
                  ></span>
                  <span class="sr-only">Active profile</span>
                {/if}
              </a>
            {/snippet}
          </Sidebar.MenuButton>
        </Sidebar.MenuItem>
      {/each}
    </Sidebar.Menu>
  </Sidebar.Group>
{/if}

{#if instrumentId && instrumentChannels.length}
  <Sidebar.Group class="py-2">
    <Sidebar.GroupLabel>Channels</Sidebar.GroupLabel>
    <Sidebar.Menu>
      {#each instrumentChannels as item (item.href)}
        {@render navigationItem(item)}
      {/each}
    </Sidebar.Menu>
  </Sidebar.Group>
{/if}

{#if activeInstrument}
  <Sidebar.Group class="border-b border-line-muted pt-2 pb-3">
    <Sidebar.GroupLabel>Sync</Sidebar.GroupLabel>
    <Sidebar.Menu>
      {#each generatorNavigation as item (item.href)}
        {@render navigationItem(item)}
      {/each}
    </Sidebar.Menu>
  </Sidebar.Group>
{/if}

{#each deviceGroups as deviceGroup (deviceGroup.id)}
  <Sidebar.Group class="py-2">
    <Sidebar.GroupLabel>{deviceGroup.label}</Sidebar.GroupLabel>
    <Sidebar.Menu>
      {#each deviceGroup.deviceIds as targetId (targetId)}
        {@const current = deviceId === targetId}
        {@const issue = deviceIssue(targetId)}
        <Sidebar.MenuItem>
          <Sidebar.MenuButton isActive={current} title={displayName(targetId)}>
            {#snippet child({ props })}
              <a {...props} href={devicePath(targetId)} aria-current={current ? 'page' : undefined}>
                <span class="truncate">{displayName(targetId)}</span>
                {#if issue}
                  <span class={`ml-auto size-1.5 shrink-0 rounded-full ${issue.class}`} title={issue.label}></span>
                  <span class="sr-only">{issue.label}</span>
                {/if}
              </a>
            {/snippet}
          </Sidebar.MenuButton>
        </Sidebar.MenuItem>
      {/each}
    </Sidebar.Menu>
  </Sidebar.Group>
{/each}
