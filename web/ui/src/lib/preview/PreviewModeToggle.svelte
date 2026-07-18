<script lang="ts">
  import { getVoxelApp, type PreviewMode } from '$lib/model';
  import { cn } from '$lib/utils';

  const view = getVoxelApp().view;

  function seg(mode: PreviewMode): string {
    return cn(
      'h-full rounded-sm px-3 text-sm transition-colors',
      view.mode === mode ? 'bg-element-selected text-fg shadow-sm' : 'text-fg-muted hover:text-fg'
    );
  }
</script>

<div class="flex h-ui-md items-center rounded-md border border-input bg-canvas/50 p-0.5">
  <button type="button" class={seg('live')} onclick={() => view.setMode('live')}>Live</button>
  <button type="button" data-fly-target class={seg('snaps')} onclick={() => view.setMode('snaps')}>Snaps</button>
  <button type="button" class={seg('stage')} onclick={() => view.setMode('stage')}>Stage</button>
</div>
