<script lang="ts">
  import { SvelteSet } from 'svelte/reactivity';

  import { page } from '$app/state';
  import { getInstrumentSelection, useAppBar } from '$lib/context.svelte';
  import type { KeyPath } from '$lib/core/types';
  import { Button, Checkbox, ObjectDiff, ObjectView } from '@voxel/kit';
  import { displayName } from '@voxel/kit/format';

  const selection = getInstrumentSelection();
  const name = $derived(page.params.instrument ?? '');
  const instrument = $derived(selection.instrument);
  const session = $derived(selection.session);

  // A profile or field that only 1 side has is compared with nothing.
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

  // A block that no longer differs drops out and is not counted.
  const checked = new SvelteSet<string>();
  const picked = $derived(blocks.filter((block) => checked.has(block.key)));
  // A save is confirmed first; no undo takes it back.
  let asking = $state(false);
  let refused = $state<string>();

  function check(key: string, on: boolean): void {
    if (on) checked.add(key);
    else checked.delete(key);
    asking = false;
  }

  /** A refusal stays on the page until the next action. */
  async function act(action: 'restore' | 'save'): Promise<void> {
    const paths = picked.map((block) => block.path);
    asking = false;
    refused = undefined;
    try {
      if (action === 'restore') await session?.restoreDefaultState(paths);
      else await session?.saveAsDefaultState(paths);
    } catch (error) {
      refused = error instanceof Error ? error.message : String(error);
    }
  }

  const VIEWS = ['changes', 'all'];
  let view = $state('changes');

  useAppBar(() => ({
    crumbs: [{ label: 'Config' }],
    actions: [
      { label: 'Show', options: VIEWS, value: view, onChange: (picked) => (view = picked), formatLabel: displayName }
    ]
  }));
</script>

<div class="page-body min-h-0 flex-1 pt-2.5">
  {#if instrument}
    <div class="flex flex-col gap-5">
      {#each blocks as block (block.key)}
        <section class="flex flex-col gap-2">
          <div class="flex items-center gap-4 px-0.5">
            <label class="flex min-w-0 cursor-pointer items-center gap-2.5">
              <!-- Only the running instrument can restore or save. -->
              {#if session}<Checkbox value={checked.has(block.key)} onChange={(on) => check(block.key, on)} />{/if}
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
  {:else if name && selection.problems(name) > 0}
    <!-- A folder with a problem has no checked state to compare. -->
    <p class="text-sm text-fg-muted">
      Cannot compare.
      <a class="text-danger-fg hover:underline" href={selection.problemsHref(name)}>
        {selection.problems(name)}
        {selection.problems(name) === 1 ? 'problem' : 'problems'}
      </a>
    </p>
  {/if}
</div>
{#if session && blocks.length > 0}
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
