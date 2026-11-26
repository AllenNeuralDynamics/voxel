<script lang="ts">
  import { page } from '$app/state';
  import { getInstrumentSelection } from '$lib/context.svelte';
  import { type OutlineKind, SpimInstrument, SpimSession, type SpimTask } from '$lib/core/spim.svelte';
  import RunCard from '$lib/features/run/RunCard.svelte';
  import RunNotes from '$lib/features/run/RunNotes.svelte';
  import { Section } from '@voxel/kit';
  import { reportFailure } from '@voxel/kit/failures';
  import * as Sortable from '@voxel/kit/sortable';

  const KINDS: Record<OutlineKind, string> = {
    bounding_box: 'Bounding box',
    convex_hull: 'Convex hull',
    explicit_points: 'Points'
  };

  const selection = getInstrumentSelection();
  const name = $derived(page.params.instrument ?? '');
  const spim = $derived(selection.instrument instanceof SpimInstrument ? selection.instrument : undefined);
  const session = $derived(selection.session instanceof SpimSession ? selection.session : undefined);
  const tasks = $derived(spim?.state.get('plan') ?? []);
  const acquisition = $derived(session?.acquisition);

  /** Planned tasks give their volume count; a task with no plan gives its reason. */
  function plan(task: SpimTask): { volumes: number } | { problem: string } | undefined {
    const planned = session?.planned(task.id);
    if (!planned) return undefined;
    if ('msg' in planned) return { problem: planned.msg };
    if (planned.stops.length === 0) return { problem: 'Has no tiles' };
    return { volumes: planned.stops.length * task.profiles.length };
  }

  function reorder(reordered: SpimTask[]): void {
    reportFailure(session?.reorderTasks(reordered.map((task) => task.id)));
  }

  function taskHref(id: string): string {
    return selection.href(name, `run/${encodeURIComponent(id)}`);
  }

  function plural(count: number, word: string): string {
    return `${count} ${word}${count === 1 ? '' : 's'}`;
  }
</script>

{#snippet count(planned: ReturnType<typeof plan>)}
  {#if planned === undefined}
    <span class="shrink-0 text-sm text-fg-muted">…</span>
  {:else if 'problem' in planned}
    <span class="shrink-0 text-sm text-danger-fg">No plan</span>
  {:else}
    <span class="shrink-0 text-sm text-fg-muted tabular-nums">{plural(planned.volumes, 'volume')}</span>
  {/if}
{/snippet}

<div class="@container/run h-full min-h-0">
  <!-- Stacked, the tasks and the notes scroll as 1 above the card. Side by side, the scroll box drops out: the tasks
  fill the left column, and on the right the notes scroll when they must so the card never does. -->
  <div
    class="grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto] @[72rem]/run:grid-cols-[minmax(0,1fr)_28rem] @[72rem]/run:grid-rows-[minmax(0,auto)_auto_minmax(0,1fr)]"
  >
    <div class="flex min-h-0 flex-col overflow-y-auto @[72rem]/run:contents">
      <div
        class="px-inset relative pt-4 pb-5 @[72rem]/run:row-span-3 @[72rem]/run:min-h-0 @[72rem]/run:overflow-y-auto @[72rem]/run:border-r @[72rem]/run:border-line-faint"
      >
        <Section heading="Tasks">
          {#if tasks.length > 0}
            <Sortable.Root
              items={tasks}
              key={(task) => task.id}
              onReorder={reorder}
              layout="vertical"
              class="flex flex-col gap-2.5 p-2"
              containerClass="-m-2"
              scroll={false}
            >
              {#snippet item(task: SpimTask)}
                {@const planned = plan(task)}
                <Sortable.Item item={task} class="flex min-w-0 items-stretch frame-raised-link">
                  <Sortable.Handle
                    item={task}
                    disabled={!session || acquisition !== undefined}
                    class="grip mr-2 w-3 shrink-0 cursor-grab touch-none rounded-l-lg text-line-faint hover:bg-tint hover:text-fg-faint active:cursor-grabbing"
                  >
                    <span class="sr-only">Move {task.id}</span>
                  </Sortable.Handle>
                  <a href={taskHref(task.id)} class="flex min-w-0 flex-1 flex-col gap-0.5 py-2 pr-3">
                    <span class="flex min-w-0 items-baseline gap-2.5">
                      <span class="min-w-0 flex-1 truncate font-mono">{task.id}</span>
                      <span class="shrink-0 text-sm text-fg-muted">{KINDS[task.region.outline.kind]}</span>
                      {@render count(planned)}
                    </span>
                    <span class="truncate font-mono text-sm text-fg-muted">{task.profiles.join(', ')}</span>
                  </a>
                </Sortable.Item>
              {/snippet}
            </Sortable.Root>
          {:else}
            <p class="text-sm text-fg-muted">No tasks</p>
          {/if}
        </Section>
      </div>
      <RunNotes
        class="px-inset mt-auto pb-4 @[72rem]/run:col-start-2 @[72rem]/run:row-start-1 @[72rem]/run:mt-0 @[72rem]/run:min-h-0 @[72rem]/run:overflow-y-auto @[72rem]/run:pt-4 @[72rem]/run:pb-0"
      />
    </div>

    <div
      class="px-inset min-h-0 overflow-y-auto border-t border-line-faint pt-4 pb-3 @[72rem]/run:col-start-2 @[72rem]/run:row-start-2 @[72rem]/run:border-t-0"
    >
      <RunCard />
    </div>
  </div>
</div>
