<script lang="ts">
  import { wavelengthToColor } from '$lib/colors.svelte';
  import type { ImagingProtocol } from '$lib/model';
  import { displayName } from '$lib/utils';

  interface Props {
    imaging: ImagingProtocol;
  }

  const { imaging }: Props = $props();
</script>

<section id="profiles" class="scroll-mt-4" aria-labelledby="profiles-heading">
  <h2 id="profiles-heading" class="mb-2 text-sm font-medium tracking-wide text-fg-faint uppercase">
    <a href="#profiles" class="hover:text-fg">Profiles</a>
  </h2>
  <div class="overflow-x-auto rounded-lg border border-border/60">
    <table class="w-full min-w-3xl table-fixed text-left">
      <colgroup>
        <col class="w-[20%]" />
        <col class="w-[34%]" />
        <col class="w-[34%]" />
        <col class="w-[12%]" />
      </colgroup>
      <thead class="border-b border-border/60 bg-element-bg/40 text-sm text-fg-faint">
        <tr>
          <th class="px-3 py-2 font-normal">Profile</th>
          <th class="px-3 py-2 font-normal">Description</th>
          <th class="px-3 py-2 font-normal">Channels</th>
          <th class="px-3 py-2 text-right font-normal">Z step</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-border/50">
        {#each Object.entries(imaging.profiles) as [profileId, profile] (profileId)}
          <tr>
            <td class="px-3 py-2.5 font-medium text-fg">{profile.label ?? displayName(profileId)}</td>
            <td class="px-3 py-2.5 text-fg-muted">{profile.desc || '—'}</td>
            <td class="px-3 py-2.5">
              <div class="flex flex-wrap gap-x-3 gap-y-1">
                {#each profile.channels as channelId (channelId)}
                  {@const channel = imaging.channels[channelId]}
                  <a
                    href={`#channel-${channelId}`}
                    class="inline-flex items-center gap-1.5 text-fg-muted transition-colors hover:text-fg hover:underline"
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
            </td>
            <td class="px-3 py-2.5 text-right font-mono text-fg">{profile.z_step} &micro;m</td>
          </tr>
        {:else}
          <tr>
            <td colspan="4" class="px-3 py-4 text-fg-muted">No profiles configured.</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</section>
