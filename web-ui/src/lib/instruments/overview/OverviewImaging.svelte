<script lang="ts">
  import { wavelengthToColor } from '$lib/colors.svelte';
  import type { ImagingProtocol } from '$lib/model';
  import { displayName } from '$lib/utils';

  interface Props {
    imaging: ImagingProtocol;
  }

  const { imaging }: Props = $props();
</script>

<section id="profiles" class="scroll-mt-12" aria-labelledby="profiles-heading">
  <h2 id="profiles-heading" class="mb-2 text-sm font-medium tracking-wide text-fg-faint uppercase">
    <a href="#profiles" class="hover:text-fg">Profiles</a>
  </h2>

  <div class="grid grid-cols-[repeat(auto-fit,minmax(min(100%,24rem),1fr))] gap-2">
    {#each Object.entries(imaging.profiles) as [profileId, profile] (profileId)}
      <article
        class="grid gap-2 rounded-lg border border-border/60 px-3 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:gap-x-6"
      >
        <div class="min-w-0">
          <h3 class="font-medium text-fg">{profile.label ?? displayName(profileId)}</h3>
          {#if profile.desc}
            <p class="mt-0.5 text-fg-muted">{profile.desc}</p>
          {/if}
        </div>

        <div class="font-mono text-sm whitespace-nowrap text-fg-muted sm:pt-0.5">
          Z step <span class="text-fg">{profile.z_step} &micro;m</span>
        </div>

        <div class="flex flex-wrap gap-1.5 sm:col-span-2">
          {#each profile.channels as channelId (channelId)}
            {@const channel = imaging.channels[channelId]}
            <a
              href={`#channel-${channelId}`}
              class="inline-flex items-center gap-1.5 rounded-md bg-element-bg px-2 py-1 text-sm text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
            >
              {#if channel?.emission}
                <span
                  class="size-1.5 shrink-0 rounded-full"
                  style="background-color: {wavelengthToColor(channel.emission)}"
                ></span>
              {/if}
              {channel?.label ?? displayName(channelId)}
            </a>
          {/each}
        </div>
      </article>
    {:else}
      <p class="rounded-lg border border-border/60 px-3 py-4 text-fg-muted">No profiles configured.</p>
    {/each}
  </div>
</section>

<section id="channels" class="mt-6 scroll-mt-12" aria-labelledby="channels-heading">
  <h2 id="channels-heading" class="mb-2 text-sm font-medium tracking-wide text-fg-faint uppercase">
    <a href="#channels" class="hover:text-fg">Channels</a>
  </h2>

  <div class="grid grid-cols-[repeat(auto-fit,minmax(min(100%,24rem),1fr))] gap-2">
    {#each Object.entries(imaging.channels) as [channelId, channel] (channelId)}
      <article id={`channel-${channelId}`} class="scroll-mt-12 rounded-lg border border-border/60 p-3">
        <div class="flex items-center gap-2">
          {#if channel.emission}
            <span class="size-2 shrink-0 rounded-full" style="background-color: {wavelengthToColor(channel.emission)}"
            ></span>
          {/if}
          <h3 class="font-medium text-fg">{channel.label ?? displayName(channelId)}</h3>
          {#if channel.emission}
            <span class="ml-auto font-mono text-sm text-fg-faint">{channel.emission} nm</span>
          {/if}
        </div>

        {#if channel.desc}
          <p class="mt-1 text-fg-muted">{channel.desc}</p>
        {/if}

        <div class="mt-3 flex min-w-0 items-center gap-2 font-mono text-sm text-fg-muted">
          <span class="truncate" title={displayName(channel.illumination)}>{displayName(channel.illumination)}</span>
          <span class="shrink-0 text-fg-faint" aria-label="to">→</span>
          <span class="truncate text-fg" title={displayName(channel.detection)}>{displayName(channel.detection)}</span>
        </div>
      </article>
    {:else}
      <p class="rounded-lg border border-border/60 px-3 py-4 text-fg-muted">No channels configured.</p>
    {/each}
  </div>
</section>
