<script lang="ts">
  import type { ResolvedPathname } from '$app/types';
  import { ChevronDown } from '$lib/icons';
  import {
    buildDeviceTopology,
    type DeviceTopologyEntry,
    groupDeviceTopology,
    targetName
  } from '$lib/instruments/device-topology';
  import { Collapsible } from '$lib/kit';
  import type { DeviceHandle, HALConfig, Instrument } from '$lib/model';
  import { cn, displayName } from '$lib/utils';

  interface Props {
    hal: HALConfig;
    devices?: Instrument['devices'];
    deviceHref?: (deviceId: string) => ResolvedPathname;
  }

  const { hal, devices, deviceHref }: Props = $props();
  const deviceGroups = $derived(groupDeviceTopology(buildDeviceTopology(hal)));
</script>

{#snippet card(entry: DeviceTopologyEntry, live: DeviceHandle | undefined)}
  <div class="flex items-center gap-2">
    <h4 class="min-w-0 flex-1 truncate text-lg font-medium text-fg" title={displayName(entry.id)}>
      {displayName(entry.id)}
    </h4>
    {#if live}
      <span
        class={cn(
          'size-1.5 shrink-0 rounded-full',
          live.error ? 'bg-danger' : live.connected ? 'bg-success' : 'bg-fg-muted'
        )}
        title={live.error ? 'Error' : live.connected ? 'Connected' : 'Disconnected'}
      ></span>
    {/if}
  </div>
  <p class="mt-0.5 truncate font-mono text-sm text-fg-muted" title={entry.config.target}>
    {targetName(entry.config.target)}
  </p>
  {#if entry.roles.length > 0}
    <div class="mt-2 flex flex-wrap gap-1">
      {#each entry.roles as role (role)}
        <span class="rounded bg-element-bg px-1.5 py-0.5 text-sm text-fg-muted">{role}</span>
      {/each}
    </div>
  {/if}
{/snippet}

<Collapsible.Root>
  <section id="devices" class="scroll-mt-4">
    <div class="mb-3 flex items-center gap-2">
      <h2 class="text-base font-medium tracking-wide text-fg-muted uppercase">
        <a href="#devices" class="hover:text-fg">Devices</a>
      </h2>
      <Collapsible.Trigger
        class="ml-auto rounded p-1 text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
        aria-label="Toggle Devices"
      >
        <ChevronDown class="size-4 -rotate-90 transition-transform duration-200 [[data-state=open]>&]:rotate-0" />
      </Collapsible.Trigger>
    </div>
    <Collapsible.Content>
      <div class="space-y-5">
        {#each deviceGroups as group (group.id)}
          <section>
            <div class="mb-2 flex items-baseline gap-2">
              <h3 class="font-medium text-fg">{displayName(group.label)}</h3>
              {#if group.node}
                <span class="text-sm text-fg-muted capitalize">{group.node.kind}</span>
                {#if group.node.address}
                  <span class="truncate font-mono text-sm text-fg-faint">{group.node.address}</span>
                {/if}
              {:else}
                <span class="text-sm text-fg-muted">In process</span>
              {/if}
            </div>

            <div class="grid grid-cols-[repeat(auto-fill,minmax(18rem,1fr))] gap-2">
              {#each group.devices as entry (entry.id)}
                {@const live = devices?.get(entry.id)}
                {@const cardClass =
                  'group rounded-lg border border-border bg-card p-3 shadow-sm transition-colors hover:border-accent hover:bg-element-hover'}
                {#if deviceHref}
                  <a href={deviceHref(entry.id)} class={cardClass}>
                    {@render card(entry, live)}
                  </a>
                {:else}
                  <div class={cardClass}>
                    {@render card(entry, live)}
                  </div>
                {/if}
              {/each}
            </div>
          </section>
        {/each}
      </div>
    </Collapsible.Content>
  </section>
</Collapsible.Root>
