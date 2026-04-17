<script lang="ts">
  import { resolve } from '$app/paths';
  import { Collapsible } from 'bits-ui';
  import { getSessionContext } from '$lib/context';
  import { sanitizeString, wavelengthToColor } from '$lib/utils';
  import { JsonView } from '$lib/kit';
  import { ChevronRight, Cog } from '$lib/icons';
  import { ProfileCard } from '$lib/profile';
  import { DeviceCard } from '$lib/device';
  import { themes } from '$lib/themes';

  const session = getSessionContext();
  const config = $derived(session.rig_cfg);

  const headingClass = 'mb-2 text-xs tracking-wide text-fg-muted uppercase';
  const cardGroupClass = 'grid auto-rows-auto grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-3';
</script>

<!-- Compact header -->
<div class="flex items-center gap-3 px-4 text-sm text-fg-muted">
  <span class="font-medium text-fg">{session.details.config.rig.name}</span>
  <div class="ml-auto flex items-center gap-3">
    <span>
      {[...session.devices.devices.values()].filter((d) => d.connected).length}/{session.devices.devices.size} devices
    </span>
    <span>&middot;</span>
    <span>{session.stacks.list.length} stacks</span>
    <button
      title="Appearance (⌘K ⌘T)"
      onclick={() => (themes.pickerOpen = true)}
      class="flex items-center text-fg-muted transition-colors hover:text-fg"
    >
      <Cog width="14" height="14" />
    </button>
  </div>
</div>

<!-- Profile cards -->
<section class="px-4 pt-4">
  <h3 class={headingClass}>Profiles</h3>
  <div class={cardGroupClass}>
    {#each Object.keys(config.profiles) as profileId (profileId)}
      <ProfileCard {session} {profileId} />
    {/each}
  </div>
</section>

<!-- Channel cards -->
<section class="px-4 pt-6">
  <h3 class={headingClass}>Channels</h3>
  <div class={cardGroupClass}>
    {#each Object.entries(config.channels) as [channelId, channel] (channelId)}
      <div class="rounded-lg border bg-card p-3 text-sm text-fg shadow-sm">
        <div class="mb-2 flex items-center gap-2">
          {#if channel.emission}
            <span
              class="h-2.5 w-2.5 shrink-0 rounded-full"
              style="background-color: {wavelengthToColor(channel.emission)}"
            ></span>
          {/if}
          <span class="font-medium text-fg">
            {channel.label ?? sanitizeString(channelId)}
          </span>
        </div>
        <div class="space-y-1 text-fg-muted">
          <div class="flex justify-between">
            <span>Detection</span>
            <span class="text-fg">{channel.detection}</span>
          </div>
          <div class="flex justify-between">
            <span>Illumination</span>
            <span class="text-fg">{channel.illumination}</span>
          </div>
          {#each Object.entries(channel.filters) as [fwId, position] (fwId)}
            <div class="flex justify-between">
              <span>{fwId}</span>
              <span class="text-fg">{position}</span>
            </div>
          {/each}
        </div>
      </div>
    {/each}
  </div>
</section>

<!-- Device cards -->
<section class="px-4 pt-6">
  <h3 class={headingClass}>Devices</h3>
  <div class={cardGroupClass}>
    {#each [...session.devices.devices.keys()] as deviceId (deviceId)}
      <DeviceCard {session} {deviceId} />
    {/each}
  </div>
</section>

<!-- Config tree -->
<section class="px-4 pt-6 pb-4">
  <Collapsible.Root>
    <Collapsible.Trigger class="group flex w-full cursor-pointer items-center justify-between text-left">
      <h3 class={headingClass}>Configuration</h3>
      <ChevronRight
        width="12"
        height="12"
        class="shrink-0 text-fg-muted transition-transform group-data-[state=open]:rotate-90"
      />
    </Collapsible.Trigger>
    <Collapsible.Content>
      <JsonView data={config} expandDepth={2} />
    </Collapsible.Content>
  </Collapsible.Root>
</section>

<!-- Debug link -->
<section class="px-4 pt-4 pb-8">
  <a href={resolve('/debug' as '/')} class="text-sm text-fg-muted transition-colors hover:text-fg"> Debug &rarr; </a>
</section>
