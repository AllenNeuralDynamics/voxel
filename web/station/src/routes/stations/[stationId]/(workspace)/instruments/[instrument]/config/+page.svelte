<script lang="ts">
  import { SvelteSet } from 'svelte/reactivity';

  import { page } from '$app/state';
  import { getVoxelStation, useAppBar } from '$lib/context.svelte';
  import type { KeyPath } from '$lib/core/types';
  import { Button, Checkbox, ObjectDiff, ObjectView } from '@voxel/kit';
  import { displayName } from '@voxel/kit/format';

  /**
   * How the state of the instrument differs from its default state, in blocks. A choice in the app bar shows only the
   * changes, or all values with the changes marked. Checked blocks go back to the default, or become the default.
   */
  const station = getVoxelStation();
  const name = $derived(page.params.instrument ?? '');
  // The model is of the open instrument, which may not be the one that the address names.
  const instrument = $derived(station.session?.instrument_name === name ? station.instrument : undefined);

  // What differs between the state and the default state, in blocks: 1 for each profile that differs, then 1 for
  // each other field that differs. A profile or a field that only 1 side has is compared with nothing.
  const blocks = $derived.by(() => {
    if (!instrument) return [];
    const [state, defaults] = [instrument.state, instrument.defaultState];
    const profiles = [...new Set([...state.profileIds, ...defaults.profileIds])].map((id) => ({
      key: `profiles/${id}`,
      path: ['profiles', id] as KeyPath,
      heading: state.profile(id)?.label || defaults.profile(id)?.label || displayName(id),
      kind: 'Profile',
      now: state.profile(id) ?? {},
      was: defaults.profile(id) ?? {}
    }));
    const fields = state.fields
      // A field that the default state does not have cannot be a default, such as the plan.
      .filter((field) => field !== 'profiles' && defaults.fields.includes(field))
      .map((field) => ({
        key: field,
        path: [field] as KeyPath,
        heading: displayName(field),
        kind: null,
        now: state.value[field as keyof typeof state.value] ?? {},
        was: defaults.value[field as keyof typeof defaults.value] ?? {}
      }));
    return [...profiles, ...fields]
      .map((block) => ({ ...block, count: ObjectDiff.count(block.now, block.was) }))
      .filter((block) => block.count > 0);
  });

  // The blocks that a person checked, by key. A block that no longer differs leaves the page, and is not counted.
  const checked = new SvelteSet<string>();
  const picked = $derived(blocks.filter((block) => checked.has(block.key)));
  // The save is asked about first, because no undo takes it back. Why the instrument refused the last action.
  let asking = $state(false);
  let refused = $state<string>();

  function check(key: string, on: boolean): void {
    if (on) checked.add(key);
    else checked.delete(key);
    asking = false;
  }

  /** Restores or saves the checked blocks. A refusal stays on the page until the next action. */
  async function act(action: 'restore' | 'save'): Promise<void> {
    const paths = picked.map((block) => block.path);
    asking = false;
    refused = undefined;
    try {
      if (action === 'restore') await instrument?.restoreDefaultState(paths);
      else await instrument?.saveAsDefaultState(paths);
    } catch (error) {
      refused = error instanceof Error ? error.message : String(error);
    }
  }

  // Only the changes show, or every value with the changes marked.
  const VIEWS = ['changes', 'all'];
  let view = $state('changes');

  useAppBar(() => ({
    crumbs: [{ label: 'Config' }],
    actions: [
      { label: 'Show', options: VIEWS, value: view, onChange: (picked) => (view = picked), formatLabel: displayName }
    ]
  }));
</script>

<div class="page-body min-h-0 flex-1 pt-4">
  {#if instrument}
    <!-- 1 block for each thing that differs: its name, then its changes. -->
    <div class="flex flex-col gap-5">
      {#each blocks as block (block.key)}
        <section class="flex flex-col gap-2">
          <!-- The block's name, with its kind before it, and at the row's end how many values differ. -->
          <div class="flex items-center gap-4 px-0.5">
            <label class="flex min-w-0 cursor-pointer items-center gap-2.5">
              <Checkbox value={checked.has(block.key)} onChange={(on) => check(block.key, on)} />
              <h2 class="flex min-w-0 items-baseline gap-2 text-base font-medium">
                {#if block.kind}<span class="text-sm font-normal text-fg-muted">{block.kind}</span>{/if}
                <span class="truncate">{block.heading}</span>
              </h2>
            </label>
            <span class="ml-auto shrink-0 text-sm text-fg-muted">
              {block.count}
              {block.count === 1 ? 'change' : 'changes'}
            </span>
          </div>
          <ObjectView data={block.now} baseline={block.was} changesOnly={view === 'changes'} />
        </section>
      {:else}
        <p class="text-fg-muted">No changes</p>
      {/each}
    </div>
  {/if}
</div>
<!-- Under the changes: why the last action was refused, then what to do with the checked blocks. A save is asked
  about first. -->
{#if blocks.length > 0}
  {#if refused}
    <p class="px-inset shrink-0 bg-danger-tint py-2 text-sm text-danger-fg" role="alert">{refused}</p>
  {/if}
  <div
    class="px-inset box-content flex min-h-ui-sm shrink-0 items-center gap-2 border-t border-line-muted bg-shell py-2 text-sm"
  >
    <label class="flex cursor-pointer items-center gap-2.5">
      <Checkbox
        value={picked.length === blocks.length}
        indeterminate={picked.length > 0 && picked.length < blocks.length}
        onChange={(on) => blocks.forEach((block) => check(block.key, on))}
      />
      Select all
    </label>
    <span class="flex-1"></span>
    {#if picked.length > 0}
      {#if asking}
        <span class="whitespace-nowrap text-fg-muted">
          Save {picked.length === 1 ? picked[0].heading : picked.length} as {picked.length === 1
            ? 'default'
            : 'defaults'}?
        </span>
        <Button variant="quiet" onclick={() => (asking = false)}>Cancel</Button>
        <Button onclick={() => act('save')}>Save as default</Button>
      {:else}
        <span class="whitespace-nowrap text-fg-muted">{picked.length} selected</span>
        <Button variant="quiet" onclick={() => act('restore')}>Restore from default</Button>
        <Button onclick={() => (asking = true)}>Save as default</Button>
      {/if}
    {/if}
  </div>
{/if}
