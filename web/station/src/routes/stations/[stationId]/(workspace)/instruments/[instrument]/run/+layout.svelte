<script lang="ts">
  import type { Snippet } from 'svelte';

  import { goto } from '$app/navigation';
  import { page as current } from '$app/state';
  import { getInstrumentSelection, useAppBar } from '$lib/context.svelte';
  import { LinearAxis } from '$lib/core/device.svelte';
  import { SpimInstrument, SpimSession, type SpimTask } from '$lib/core/spim.svelte';
  import type { SpecimenAxis } from '$lib/core/types';
  import StageView from '$lib/features/stage/StageView.svelte';
  import { Button, buttonVariants, Dialog, DropdownMenu } from '@voxel/kit';
  import { reportFailure } from '@voxel/kit/failures';
  import { Plus, Trash } from '@voxel/kit/icons';
  import { SplitView } from '@voxel/kit/pane';

  import type { LayoutProps } from './$types';

  let { children }: LayoutProps = $props();

  const AXES: SpecimenAxis[] = ['x', 'y', 'z'];
  // A new task's depth on the scan axis when no other task gives one.
  const DEPTH_UM = 100;

  const selection = getInstrumentSelection();
  const name = $derived(current.params.instrument ?? '');
  const taskId = $derived(current.params.taskId);
  const spim = $derived(selection.instrument instanceof SpimInstrument ? selection.instrument : undefined);
  const session = $derived(selection.session instanceof SpimSession ? selection.session : undefined);
  const tasks = $derived(spim?.state.get('plan') ?? []);
  const running = $derived(session?.acquisition !== undefined);
  const scanAxis = $derived(spim?.config?.scan.axis);
  const tiled = $derived(AXES.filter((axis) => axis !== scanAxis));
  const stageAt = $derived.by(() => {
    const config = spim?.config;
    if (!config || !session) return undefined;
    const at = AXES.map((axis) => session.device(config.stage[axis].device, LinearAxis)?.position);
    return at.every((value) => value !== undefined)
      ? Object.fromEntries(AXES.map((axis, i) => [axis, at[i]!]))
      : undefined;
  });
  const canAdd = $derived(!!session && !!spim && !running && stageAt !== undefined);

  let controls = $state<Snippet>();
  let confirming = $state(false);

  function taskHref(id: string): string {
    return selection.href(name, `run/${encodeURIComponent(id)}`);
  }

  useAppBar(() => ({
    crumbs:
      taskId === undefined
        ? [{ label: 'Run' }]
        : [
            { label: 'Run', href: selection.href(name, 'run') },
            { label: taskId, items: tasks.map((task) => ({ label: task.id, href: taskHref(task.id) })) }
          ],
    actions: [
      taskId === undefined
        ? { bar: addBar, menu: addItems }
        : {
            label: 'Delete',
            icon: Trash,
            danger: true,
            disabled: !session || running,
            onclick: () => (confirming = true)
          },
      ...(controls ? [{ bar: controls }] : [])
    ]
  }));

  /** At the stage: 1 tile of the active profile around it, or the stage position as 1 point. */
  async function add(kind: 'area' | 'position'): Promise<void> {
    if (!session || !stageAt || scanAxis === undefined) return;
    const at = stageAt;
    const [a, b] = tiled;
    let points;
    if (kind === 'area') {
      const tile = session.newTaskTile;
      const spanA = tile?.[a];
      const spanB = tile?.[b];
      if (!spanA || !spanB) return;
      points = [
        { [a]: at[a] + spanA[0], [b]: at[b] + spanB[0] },
        { [a]: at[a] + spanA[1], [b]: at[b] + spanB[1] }
      ];
    } else {
      points = [{ [a]: at[a], [b]: at[b] }];
    }
    const last = tasks.at(-1)?.region.bounds;
    const depth = last ? Math.abs(last[1] - last[0]) : DEPTH_UM;
    const task = session.draftTask(kind === 'area' ? 'bounding_box' : 'explicit_points', points, [
      at[scanAxis],
      at[scanAxis] + depth
    ]);
    if (!task) return;
    await session.addTask(task);
    await goto(taskHref(task.id));
  }

  async function remove(): Promise<void> {
    confirming = false;
    if (!session || taskId === undefined) return;
    await session.removeTasks([taskId]);
    await goto(selection.href(name, 'run'));
  }
</script>

{#snippet addBar()}
  <DropdownMenu.Root>
    <DropdownMenu.Trigger
      class={buttonVariants({ variant: 'secondary', size: 'md', class: 'text-base' })}
      disabled={!canAdd}
    >
      <Plus class="size-4" aria-hidden="true" />Add task
    </DropdownMenu.Trigger>
    <DropdownMenu.Content align="end" sideOffset={6} class="min-w-48">
      {@render addItems()}
    </DropdownMenu.Content>
  </DropdownMenu.Root>
{/snippet}

{#snippet addItems()}
  <DropdownMenu.Item disabled={!canAdd || !session?.newTaskTile} onclick={() => reportFailure(add('area'))}>
    An area of 1 tile
  </DropdownMenu.Item>
  <DropdownMenu.Item disabled={!canAdd} onclick={() => reportFailure(add('position'))}>
    The stage position
  </DropdownMenu.Item>
{/snippet}

<Dialog.Root bind:open={confirming}>
  <Dialog.Content size="sm" showCloseButton={false}>
    <Dialog.Header>
      <Dialog.Title>Delete task <span class="font-mono">{taskId}</span></Dialog.Title>
      <Dialog.Description>Undo brings it back.</Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button variant="secondary" onclick={() => (confirming = false)}>Cancel</Button>
      <Button variant="danger" onclick={() => reportFailure(remove())}>Delete</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

<SplitView
  persist="run"
  main="stage"
  panes={{
    page: { horizontal: { min: 32, default: 32, max: 48 }, vertical: { min: 28, default: 28 } },
    stage: { horizontal: { min: 32 }, vertical: { min: 10 } }
  }}
  bind:controls
>
  {#snippet page()}
    {@render children()}
  {/snippet}
  {#snippet stage()}
    <div class="h-full min-h-0 min-w-0 overflow-hidden"><StageView /></div>
  {/snippet}
</SplitView>
