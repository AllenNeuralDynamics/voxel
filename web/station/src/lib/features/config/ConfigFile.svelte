<script lang="ts">
  import { page } from '$app/state';
  import { getInstrumentSelection, getVoxelStation, useAppBar } from '$lib/context.svelte';
  import { LEVEL_ICONS } from '$lib/core/levels';
  import type { FolderFileName, Problem } from '$lib/core/station.svelte';
  import { ObjectDiff, ObjectView, type ObjectMark } from '@voxel/kit';

  /**
   * One instrument file with its problems placed under their keys. Reads the inspection, so it also works for closed or
   * failing instruments. Without `state.json` on disk, the default's content is shown, since the instrument starts from it.
   */
  let { file, expandDepth = 2 }: { file: FolderFileName; expandDepth?: number } = $props();

  const station = getVoxelStation();
  const name = $derived(page.params.instrument ?? '');
  const inspection = $derived(station.inspections[name]);
  const live = $derived(getInstrumentSelection().session);

  const problems = $derived((inspection?.problems ?? []).filter((problem) => problem.loc[0] === file));
  const read = $derived(inspection?.files?.[file]);
  const missing = $derived(file === 'state' && read !== undefined && read.data === null && problems.length === 0);
  const data = $derived(
    file === 'state' && live ? live.instrument.state.value : missing ? inspection?.files?.default.data : read?.data
  );
  // Unchecked content: the rig it is checked against has a problem.
  const waits = $derived(
    read !== undefined && read.data !== null && read.model === null && problems.length === 0 && !missing
  );

  // A problem at a missing key goes under the nearest present ancestor; one with no key shows above the content.
  const placed = $derived(
    problems.map((problem) => {
      const path: (string | number)[] = [];
      let at: unknown = data;
      for (const key of problem.loc.slice(1)) {
        const parts = ObjectDiff.parts(at);
        if (!parts || !(String(key) in parts)) break;
        path.push(key);
        at = parts[String(key)];
      }
      return { problem, path };
    })
  );
  const marks = $derived(
    placed
      .filter(({ path }) => path.length > 0)
      .map(({ problem, path }): ObjectMark => ({ path, content: note, data: problem }))
  );
  const loose = $derived(placed.filter(({ path }) => path.length === 0).map(({ problem }) => problem));

  useAppBar(() => ({ crumbs: [{ label: 'Config' }] }));
</script>

{#snippet line(problem: Problem)}
  {@const Icon = LEVEL_ICONS[problem.level]}
  <p class={['flex items-start gap-1.5', problem.level === 'warning' ? 'text-warning-fg' : 'text-danger-fg']}>
    <Icon class="mt-[0.2em] size-3.5 shrink-0" aria-hidden="true" />
    <span class="min-w-0">{problem.msg}</span>
  </p>
{/snippet}

{#snippet note(problem: unknown)}{@render line(problem as Problem)}{/snippet}

<div class="flex page-body min-h-0 flex-1 flex-col gap-3 pt-2.5">
  {#if waits}
    <p class="text-sm text-fg-muted">Not checked. rig.yaml has problems.</p>
  {/if}
  {#if loose.length > 0}
    <div class="flex flex-col gap-1 text-sm">
      {#each loose as problem, index (index)}{@render line(problem)}{/each}
    </div>
  {/if}
  {#if data !== undefined && data !== null}
    <ObjectView {data} {expandDepth} blockMarks={marks} />
  {/if}
</div>
