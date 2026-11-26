<script lang="ts">
  import { page } from '$app/state';
  import { getInstrumentSelection, getVoxelStation } from '$lib/context.svelte';
  import { LEVEL_ICONS } from '$lib/core/levels';
  import { Prefs } from '$lib/core/prefs';
  import { SpimSession } from '$lib/core/spim.svelte';
  import type { RunResult } from '$lib/core/station.svelte';
  import { Section } from '@voxel/kit';
  import { ChevronDown } from '@voxel/kit/icons';

  let { class: className }: { class?: string } = $props();

  const RESULTS: Record<RunResult, { label: string; tone: string }> = {
    completed: { label: 'Completed', tone: 'text-success-fg' },
    cancelled: { label: 'Stopped', tone: 'text-warning-fg' },
    interrupted: { label: 'Interrupted', tone: 'text-warning-fg' },
    failed: { label: 'Failed', tone: 'text-danger-fg' }
  };
  const FACTS = 'grid grid-cols-[6rem_minmax(0,1fr)] gap-x-3 px-1.5 py-0.5';

  const station = getVoxelStation();
  const selection = getInstrumentSelection();
  const name = $derived(page.params.instrument ?? '');
  const session = $derived(selection.session instanceof SpimSession ? selection.session : undefined);
  const running = $derived(session?.acquisition !== undefined);
  const run = $derived(running ? undefined : station.lastRun);
  const problems = $derived(running ? [] : (session?.startProblems(Prefs.operator.get()) ?? []));
  // The first problem shows in 1 line; the rest wait behind a toggle.
  let problemsOpen = $state(false);
  const shownProblems = $derived(problemsOpen ? problems : problems.slice(0, 1));

  function taskHref(id: string): string {
    return selection.href(name, `run/${encodeURIComponent(id)}`);
  }
</script>

{#if run?.result || problems.length > 0}
  <div class={['flex flex-col gap-4', className]}>
    {#if run?.result}
      {@const shown = RESULTS[run.result]}
      {@const finished = run.visits.filter((visit) => visit.result === 'completed').length}
      <Section heading="Last run">
        {#snippet trailing()}
          <span class={['text-sm', shown.tone]}>{shown.label}</span>
        {/snippet}
        <div class="frame-raised p-2.5">
          <div class="-mx-1.5 flex flex-col gap-0.5 text-sm">
            <div class={FACTS}>
              <span class="text-fg-muted">Volumes</span>
              <span class="tabular-nums">{finished} of {run.visits.length} finished</span>
            </div>
            <div class={FACTS}>
              <span class="text-fg-muted">Wrote to</span>
              <span class="truncate font-mono">{SpimSession.storageLabel(run.storage)}</span>
            </div>
          </div>
        </div>
      </Section>
    {/if}
    {#if problems.length > 0}
      <Section heading="Problems" id="run-problems">
        <ul class="flex flex-col gap-0.5 frame-raised p-2.5 text-sm">
          {#each shownProblems as problem, index (index)}
            {@const Icon = LEVEL_ICONS[problem.level]}
            <li>
              {#if problem.task}
                <a
                  href={taskHref(problem.task)}
                  class="-mx-1.5 flex items-center gap-2 rounded-sm px-1.5 py-0.5 hover:bg-element-hover"
                >
                  <Icon class="size-3.5 shrink-0 text-danger-fg" aria-hidden="true" />
                  <span class={['min-w-0 flex-1', !problemsOpen && 'line-clamp-1']}
                    ><span class="font-mono">{problem.task}</span>: {problem.text}</span
                  >
                </a>
              {:else}
                <span class="flex items-center gap-2 py-0.5">
                  <Icon class="size-3.5 shrink-0 text-danger-fg" aria-hidden="true" />
                  <span class={['min-w-0 flex-1', !problemsOpen && 'line-clamp-1']}>{problem.text}</span>
                </span>
              {/if}
            </li>
          {/each}
          {#if problems.length > 1}
            <li>
              <button
                type="button"
                class="-mx-1.5 flex w-[calc(100%+0.75rem)] cursor-pointer items-center gap-2 rounded-sm px-1.5 py-0.5 text-left text-fg-muted hover:bg-element-hover focus-visible:outline-2 focus-visible:outline-focus"
                aria-expanded={problemsOpen}
                onclick={() => (problemsOpen = !problemsOpen)}
              >
                <ChevronDown
                  class={['size-3.5 shrink-0 transition-transform', !problemsOpen && '-rotate-90']}
                  aria-hidden="true"
                />
                {problemsOpen ? 'Show less' : `${problems.length - 1} more`}
              </button>
            </li>
          {/if}
        </ul>
      </Section>
    {/if}
  </div>
{/if}
