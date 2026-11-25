<script lang="ts">
  import ProfileBar from '$lib/features/profiles/ProfileBar.svelte';
  import { AutoSplit } from '@voxel/kit/pane';
</script>

<ProfileBar place="timing" label="Timing" />

<AutoSplit
  persist="timing"
  panes={{
    view: { horizontal: { min: 32 }, vertical: { min: 10 } },
    inspector: { horizontal: { min: 26, default: 26, max: 34 }, vertical: { min: 8, default: 16 } }
  }}
>
  {#snippet view()}
    <div class="h-full min-h-0 min-w-0 overflow-hidden"></div>
  {/snippet}
  {#snippet inspector()}
    <div class="h-full page-body pt-4"></div>
  {/snippet}
</AutoSplit>
