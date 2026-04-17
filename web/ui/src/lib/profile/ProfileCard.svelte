<script lang="ts">
  import type { Session } from '$lib/app';
  import { sanitizeString, wavelengthToColor } from '$lib/utils';

  interface Props {
    session: Session;
    profileId: string;
  }

  let { session, profileId }: Props = $props();

  const profile = $derived(session.rig_cfg.profiles[profileId]);
  const channels = $derived(session.rig_cfg.channels);
  const isActive = $derived(profileId === session.profiles.activeId);

  function activate() {
    session.profiles.setActive(profileId);
  }
</script>

{#if profile}
  <div class="rounded-lg border bg-card p-3 text-sm text-fg shadow-sm">
    <div class="mb-2 flex items-center justify-between gap-2">
      <span class="truncate font-medium text-fg">
        {profile.label ?? sanitizeString(profileId)}
      </span>
      {#if isActive}
        <span class="shrink-0 rounded-full bg-success/15 px-1.5 py-px text-center text-xs font-medium text-success">
          Active
        </span>
      {:else}
        <button
          class="shrink-0 cursor-pointer rounded-full border border-fg-faint px-1.5 py-px text-center text-xs font-medium text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
          onclick={activate}
        >
          Activate
        </button>
      {/if}
    </div>
    {#if profile.desc}
      <p class="mb-2 text-fg-muted">{profile.desc}</p>
    {/if}
    {#if profile.channels.length > 0}
      <div class="flex flex-wrap gap-1.5">
        {#each profile.channels as channelId (channelId)}
          {@const ch = channels[channelId]}
          {#if ch}
            <span class="flex items-center gap-1 rounded bg-element-bg px-1.5 py-0.5 text-xs text-fg-muted">
              {#if ch.emission}
                <span class="h-1.5 w-1.5 rounded-full" style="background-color: {wavelengthToColor(ch.emission)}"
                ></span>
              {/if}
              {ch.label ?? sanitizeString(channelId)}
            </span>
          {/if}
        {/each}
      </div>
    {/if}
  </div>
{/if}
