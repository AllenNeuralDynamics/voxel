<script lang="ts">
  import type { Session } from '$lib/main';
  import type { LayerVisibility } from '$lib/main/types';
  import StagePosition from './StagePosition.svelte';
  import { offsetControl, overlapControl, zDefaults } from './helpers.svelte';
  import XYPlane from './XYPlane.svelte';
  import ZPlane from './ZPlane.svelte';
  import { slide } from 'svelte/transition';

  interface Props {
    session: Session;
  }

  let { session }: Props = $props();

  let layers = $state<LayerVisibility>({ grid: false, stacks: true, path: true, fov: true, thumbnail: true });
</script>

{#if session.stage && session.stage.x && session.stage.y && session.stage.z}
  {@const gc = session.rig_cfg.profiles[session.activeProfileId ?? '']?.grid ?? null}
  <div class="flex h-full flex-col">
    <div class="flex min-h-0 min-w-0 flex-1 items-stretch gap-4 px-4 py-4">
      <XYPlane {session} bind:layers />
      <ZPlane {session} />
    </div>
    {#if gc && layers.grid}
      <div
        transition:slide={{ duration: 200 }}
        class="flex w-full flex-wrap items-center justify-between gap-4 border-t border-border px-4 py-2"
      >
        {@render offsetControl(session, gc)}
        {@render overlapControl(session, gc)}
      </div>
    {/if}
    <div class="flex w-full flex-wrap items-center justify-between gap-4 border-t border-border px-4 py-2">
      {@render zDefaults(session)}
      <StagePosition stage={session.stage} />
    </div>
  </div>
{:else}
  <div class="grid h-full w-full place-content-center">
    <p class="text-base text-fg-muted">Stage not available</p>
  </div>
{/if}
