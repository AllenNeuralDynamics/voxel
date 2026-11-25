<script lang="ts">
  import { page } from '$app/state';
  import { getInstrumentSelection, getVoxelStation, useAppBar } from '$lib/context.svelte';
  import type { FolderFileName, Problem } from '$lib/core/station.svelte';
  import { ObjectDiff, ObjectView, type ObjectMark } from '@voxel/kit';
  import { TriangleAlert } from '@voxel/kit/icons';

  /**
   * 1 file of an instrument's folder, as its content, with each problem of the file under the key it is at. It reads
   * the inspection of the instrument, so it shows an instrument that is not open, and one that cannot open. The
   * state of the open instrument comes from the feed, which has every edit at once. With no `state.json` on disk, the
   * state is the default's content, because the instrument starts from it.
   */
  let { file, expandDepth = 2 }: { file: FolderFileName; expandDepth?: number } = $props();

  const station = getVoxelStation();
  const name = $derived(page.params.instrument ?? '');
  const inspection = $derived(station.inspections[name]);
  const live = $derived(getInstrumentSelection().session);

  const problems = $derived((inspection?.problems ?? []).filter((problem) => problem.loc[0] === file));
  const read = $derived(inspection?.files?.[file]);
  // A state that is not on disk has no content and no problem.
  const missing = $derived(file === 'state' && read !== undefined && read.data === null && problems.length === 0);
  const data = $derived(
    file === 'state' && live ? live.instrument.state.value : missing ? inspection?.files?.default.data : read?.data
  );
  // The file has content that was not checked: the rig, which it is checked against, has a problem.
  const waits = $derived(
    read !== undefined && read.data !== null && read.model === null && problems.length === 0 && !missing
  );

  // Each problem goes under its key. A problem at a key that the file leaves out goes under the nearest key above it
  // that the file has; one at no key of the file shows above the content.
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
  <p class={['flex items-start gap-1.5', problem.level === 'warning' ? 'text-warning-fg' : 'text-danger-fg']}>
    <TriangleAlert class="mt-[0.2em] size-3.5 shrink-0" aria-hidden="true" />
    <span class="min-w-0">{problem.msg}</span>
  </p>
{/snippet}

<!-- A mark gives back the problem that it was made with. -->
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
