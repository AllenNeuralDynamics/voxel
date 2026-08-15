<script lang="ts">
  import { ChevronDown } from '$lib/icons';
  import { pref } from '$lib/utils';

  import PreviewChannelPrefs from './PreviewChannelPrefs.svelte';
  import type { PreviewSession } from './session.svelte';

  interface Props {
    previewer: PreviewSession;
  }

  let { previewer }: Props = $props();

  const channelsVisible = pref('preview:channels-visible', true);
  const namedChannels = $derived(previewer.channels.filter((c) => c.name));
</script>

<div class="pointer-events-auto flex w-full flex-col overflow-hidden overlay-panel">
  {#if channelsVisible.get()}
    <div class="divide-y divide-border border-b border-border">
      {#each namedChannels as channel (channel.idx)}
        <div class="px-2.5 py-2">
          <PreviewChannelPrefs {previewer} {channel} />
        </div>
      {/each}
    </div>
  {/if}

  <div class="flex items-center gap-2 px-2.5 py-1">
    <span class="flex-1 text-sm text-fg-muted">
      {namedChannels.length}
      {namedChannels.length === 1 ? 'channel' : 'channels'}
    </span>
    <button
      type="button"
      onclick={() => channelsVisible.set(!channelsVisible.get())}
      class="flex h-6 w-4 shrink-0 cursor-pointer items-center justify-center rounded text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
      aria-expanded={channelsVisible.get()}
      aria-label={channelsVisible.get() ? 'Hide channels' : 'Show channels'}
      title={channelsVisible.get() ? 'Hide channels' : 'Show channels'}
    >
      <ChevronDown width="14" height="14" class="transition-transform {channelsVisible.get() ? '' : 'rotate-180'}" />
    </button>
  </div>
</div>
