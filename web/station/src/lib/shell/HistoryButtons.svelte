<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import { useShortcut } from '$lib/shell/shortcuts';
  import { Button } from '@voxel/kit';
  import { reportFailure } from '@voxel/kit/failures';
  import { Redo, Undo } from '@voxel/kit/icons';

  const app = getVoxelStation();

  for (const [id, action] of [
    ['undo', 'undo'],
    ['redo', 'redo'],
    ['redoWithY', 'redo']
  ] as const) {
    useShortcut(
      id,
      (event) => {
        if (event.defaultPrevented || event.isComposing || event.repeat) return;
        const instrument = app.instrument;
        if (!instrument || !app.canReplayHistory || instrument.history[`${action}_label`] === null) return;
        event.preventDefault();
        reportFailure(app.replay(action));
      },
      // Preserve native editing and only consume shortcuts that pass our guards.
      { preventDefault: false, stopPropagation: false }
    );
  }
</script>

{#if app.instrument}
  {@const instrument = app.instrument}
  {#each ['undo', 'redo'] as const as action (action)}
    {@const label = action === 'undo' ? 'Undo' : 'Redo'}
    {@const edit = instrument.history[`${action}_label`]}
    {@const title = edit === null ? `Nothing to ${action}` : `${label}: ${edit}`}
    <span class="shrink-0" {title}>
      <Button
        variant="ghost"
        class="text-fg-muted disabled:opacity-40"
        aria-label={title}
        disabled={!app.canReplayHistory || edit === null}
        onclick={() => reportFailure(app.replay(action))}
      >
        {#if action === 'undo'}
          <Undo />
        {:else}
          <Redo />
        {/if}
        <span class="max-lg:hidden">{label}</span>
      </Button>
    </span>
  {/each}
{/if}
