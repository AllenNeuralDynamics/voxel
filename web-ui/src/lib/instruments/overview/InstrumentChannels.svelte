<script lang="ts">
  import { wavelengthToColor } from '$lib/colors.svelte';
  import type { ImagingProtocol } from '$lib/model';
  import { displayName } from '$lib/utils';

  interface Props {
    channels: ImagingProtocol['channels'];
  }

  const { channels }: Props = $props();
</script>

<section id="channels" class="scroll-mt-4" aria-labelledby="channels-heading">
  <h2 id="channels-heading" class="mb-2 text-sm font-medium tracking-wide text-fg-faint uppercase">
    <a href="#channels" class="hover:text-fg">Channels</a>
  </h2>
  <div class="overflow-x-auto rounded-lg border border-border/60">
    <table class="w-full min-w-3xl table-fixed text-left">
      <colgroup>
        <col class="w-[20%]" />
        <col class="w-[36%]" />
        <col class="w-[22%]" />
        <col class="w-[22%]" />
      </colgroup>
      <thead class="border-b border-border/60 bg-element-bg/40 text-sm text-fg-faint">
        <tr>
          <th class="px-3 py-2 font-normal">Channel</th>
          <th class="px-3 py-2 font-normal">Description</th>
          <th class="px-3 py-2 font-normal">Detection</th>
          <th class="px-3 py-2 font-normal">Illumination</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-border/50">
        {#each Object.entries(channels) as [channelId, channel] (channelId)}
          <tr id={`channel-${channelId}`} class="scroll-mt-4">
            <td class="px-3 py-2.5">
              <span class="flex items-center gap-2 font-medium text-fg">
                {#if channel.emission}
                  <span
                    class="size-2 shrink-0 rounded-full"
                    style="background-color: {wavelengthToColor(channel.emission)}"
                  ></span>
                {/if}
                {channel.label ?? displayName(channelId)}
              </span>
            </td>
            <td class="px-3 py-2.5 text-fg-muted">{channel.desc || '—'}</td>
            <td class="px-3 py-2.5 text-fg">{displayName(channel.detection)}</td>
            <td class="px-3 py-2.5 text-fg">{displayName(channel.illumination)}</td>
          </tr>
        {:else}
          <tr>
            <td colspan="4" class="px-3 py-4 text-fg-muted">No channels configured.</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</section>
