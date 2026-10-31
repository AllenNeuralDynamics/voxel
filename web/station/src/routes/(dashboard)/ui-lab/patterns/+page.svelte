<script lang="ts">
  import { resolve } from '$app/paths';
  import DivergenceDot from '$lib/features/imaging/DivergenceDot.svelte';
  import ChipRow from '$lib/features/live/ChipRow.svelte';
  import ChoiceChip from '$lib/features/live/ChoiceChip.svelte';
  import PageHeader from '$lib/shell/PageHeader.svelte';
  import { Button, NumberInput, RadioBar, Slider, TextBox } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { ArrowRight, Check, CircleAlert, DotsSpinner, Plus, Square, TriangleAlert } from '@voxel/kit/icons';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';

  const here = resolve('/(dashboard)/ui-lab/patterns');

  const STATUS = {
    running: { label: 'Running', icon: DotsSpinner, color: 'text-fg-muted' },
    done: { label: 'Done', icon: Check, color: 'text-fg-muted' },
    stopped: { label: 'Stopped', icon: Square, color: 'text-fg-muted' },
    failed: { label: 'Failed', icon: CircleAlert, color: 'text-danger-fg' },
    interrupted: { label: 'Interrupted', icon: TriangleAlert, color: 'text-warning-fg' }
  };
  type Run = { id: string; microscope: string; time: string; done: number; total: number; status: keyof typeof STATUS };
  const DAYS: { label: string; runs: Run[] }[] = [
    {
      label: 'Today',
      runs: [
        { id: 'brain-07', microscope: 'Bench 1', time: '10:42 – 13:25', done: 18, total: 42, status: 'running' },
        { id: 'kidney-02', microscope: 'Bench 4', time: '09:41 – 09:58', done: 2, total: 10, status: 'failed' },
        { id: 'brain-06b', microscope: 'Bench 1', time: '07:15 – 08:10', done: 12, total: 12, status: 'done' }
      ]
    },
    {
      label: 'Yesterday',
      runs: [
        { id: 'brain-06', microscope: 'Bench 3', time: '16:20 – 19:05', done: 24, total: 24, status: 'done' },
        { id: 'test-1020', microscope: 'Bench 1', time: '15:30 – 15:52', done: 3, total: 8, status: 'stopped' },
        { id: 'heart-00', microscope: 'Bench 2', time: '14:00 – 14:48', done: 4, total: 9, status: 'interrupted' }
      ]
    }
  ];
  const FACTS = [
    ['Microscope', 'Bench 1'],
    ['Instrument', 'ExaSPIM'],
    ['Operator', 'jlee'],
    ['Volumes', '18 of 42'],
    ['Started', 'Today, 10:42'],
    ['Ends about', '13:25']
  ];
  const FILTERS = ['BP525', 'BP600', 'BP700'];
  const LOGS = [
    { time: '10:42:03', level: 'info', text: 'Acquisition brain-07 started' },
    { time: '10:42:05', level: 'info', text: 'camera_1 streaming at 6.0 fps' },
    { time: '10:58:11', level: 'warning', text: 'fw_emission did not reach BP525 in 2 s' },
    { time: '11:02:40', level: 'info', text: 'Tile 18 of 42 done' }
  ];

  let selectedRun = $state('brain-07');
  let grouping = $state('type');
  let source = $state(12);
  let output = $state(69.6);
  let exposure = $state(9.35);
  let filter = $state('BP600');
  let search = $state('');
</script>

{#snippet settingRow(
  name: string,
  value: number,
  set: (next: number) => void,
  max: number,
  units: string,
  reading?: string,
  changed = false
)}
  <div class="flex h-ui-sm min-w-0 items-stretch gap-2" role="group" aria-label={name}>
    <span class="flex w-20 shrink-0 items-center gap-1 text-sm text-fg-muted">
      {name}
      <DivergenceDot
        {changed}
        title="Saved: 10 {units}. Click to put it back."
        label="{name} differs from the saved profile."
        onRevert={() => set(10)}
      />
    </span>
    <div class="min-w-0 flex-1"><Slider {value} onChange={set} min={0} {max} aria-label={name} /></div>
    <div
      class="flex w-22 shrink-0 items-center gap-1 rounded-sm bg-element-bg px-2 font-mono text-sm tabular-nums focus-within:bg-element-active hover:bg-element-hover"
    >
      <NumberInput
        {value}
        onChange={set}
        min={0}
        {max}
        align="right"
        class="min-w-0 flex-1 text-fg"
        aria-label={name}
      />
      <span class="shrink-0 text-fg-muted">{units}</span>
    </div>
    <span class="flex w-20 shrink-0 items-center justify-end px-1 font-mono text-sm text-fg-muted tabular-nums">
      {reading ?? ''}
    </span>
  </div>
{/snippet}

<LabHeader title="Patterns" />

<div class={lab.body}>
  <section class={lab.section}>
    <h2 class={lab.heading}>Page header</h2>
    <div class="overflow-hidden frame-bordered bg-pane">
      <PageHeader items={[{ label: 'Profiles', href: here }, { label: 'Tile scan' }]}>
        {#snippet trailing()}
          <span class="text-sm text-fg-muted">Group by</span>
          <RadioBar
            value={grouping}
            options={['node', 'type']}
            formatLabel={(option) => (option === 'node' ? 'Node' : 'Type')}
            onChange={(option) => (grouping = option)}
            aria-label="Group by"
          />
        {/snippet}
      </PageHeader>
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Table</h2>
    <div class="frame-raised px-2 pt-1 pb-2">
      <table class="w-full border-separate border-spacing-0 text-left text-base">
        <thead>
          <tr>
            {#each ['Run', 'Microscope', 'Time', 'Volumes', 'Status'] as heading (heading)}
              <th scope="col" class="h-8 border-b border-line-faint px-2.5 text-sm font-normal text-fg-muted">
                {heading}
              </th>
            {/each}
            <th scope="col" class="w-px border-b border-line-faint"><span class="sr-only">Open</span></th>
          </tr>
        </thead>
        {#each DAYS as day (day.label)}
          <tbody>
            <tr>
              <th colspan="6" scope="colgroup" class="px-2.5 pt-4 pb-1 text-sm font-medium text-fg-muted"
                >{day.label}</th
              >
            </tr>
            {#each day.runs as run, index (run.id)}
              {@const status = STATUS[run.status]}
              {@const Icon = status.icon}
              {@const selected = run.id === selectedRun}
              {@const cell = cn(
                'h-10 px-2.5 whitespace-nowrap transition-colors first:rounded-l-md last:rounded-r-md group-hover:bg-tint',
                index > 0 && 'border-t border-line-faint',
                'group-hover:border-transparent [tr:hover+tr>&]:border-transparent',
                selected &&
                  'border-transparent bg-element-selected group-hover:bg-element-selected [tr.selected+tr>&]:border-transparent'
              )}
              <tr class={cn('group cursor-pointer', selected && 'selected')} onclick={() => (selectedRun = run.id)}>
                <td class={cell}><span class="font-mono text-fg">{run.id}</span></td>
                <td class={cell}>{run.microscope}</td>
                <td class="{cell} tabular-nums">{run.time}</td>
                <td class="{cell} tabular-nums">
                  {#if run.status === 'running'}
                    <span class="inline-flex items-center gap-2">
                      <span class="block h-1.5 w-12 overflow-hidden rounded-full bg-track">
                        <span
                          class="block h-full rounded-full bg-success-muted"
                          style:width="{(run.done / run.total) * 100}%"
                        ></span>
                      </span>
                      {run.done} of {run.total}
                    </span>
                  {:else}
                    {run.done} of {run.total}
                  {/if}
                </td>
                <td class={cell}>
                  <span class="inline-flex items-center gap-1.5 {status.color}">
                    <Icon class="size-3.5" aria-hidden="true" />{status.label}
                  </span>
                </td>
                <td class="{cell} text-fg-muted"><ArrowRight class="size-3.5" aria-hidden="true" /></td>
              </tr>
            {/each}
          </tbody>
        {/each}
      </table>
    </div>
  </section>

  <div class="grid grid-cols-2 gap-x-6 gap-y-12">
    <section class={lab.section}>
      <h2 class={lab.heading}>Facts</h2>
      <dl class="grid grid-cols-3 gap-x-4 gap-y-3 frame-raised px-4 py-3.5">
        {#each FACTS as [term, value] (term)}
          <div class="flex min-w-0 flex-col">
            <dt class="text-sm text-fg-muted">{term}</dt>
            <dd class="text-base text-fg tabular-nums">{value}</dd>
          </div>
        {/each}
      </dl>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Empty</h2>
      <div class="flex flex-col items-center gap-1 frame-raised px-4 py-7 text-center">
        <span class="text-base font-medium text-fg">No presets yet</span>
        <span class="text-base text-fg-muted">Save the settings of a run as a preset.</span>
        <Button variant="secondary" class="mt-3"><Plus class="size-3.5" />Save as preset</Button>
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Setting rows</h2>
      <div class="flex flex-col gap-3 frame-raised p-2.5">
        {@render settingRow('Source', source, (next) => (source = next), 50, 'mW', '11.8 mW', source !== 10)}
        {@render settingRow('Output', output, (next) => (output = next), 100, '%', '13.4 mW')}
        {@render settingRow('Exposure', exposure, (next) => (exposure = next), 100, 'ms')}
        <ChipRow
          label="Filters"
          restorable={filter !== 'BP525'}
          restoreTitle="Move the wheel to BP525"
          restoreLabel="Restore the filter"
          onRestore={() => (filter = 'BP525')}
        >
          <ChoiceChip
            text={filter}
            tone="text-fg"
            title="Fw Emission is at {filter}."
            options={FILTERS.map((option) => ({ value: option, label: option, marked: option === 'BP525' }))}
            value={filter}
            mark={{ label: 'Profile filter', title: 'The profile uses this filter' }}
            onChange={(next) => (filter = next)}
            footer={{ name: 'Fw Emission', href: here, title: 'Open Fw Emission' }}
          />
        </ChipRow>
      </div>
    </section>

    <section class={lab.section}>
      <h2 class={lab.heading}>Bar and framed list</h2>
      <div class="flex h-[15.5rem] flex-col overflow-hidden frame-bordered bg-pane">
        <div class="bottom-panel-bar">
          <TextBox
            live
            size="sm"
            value={search}
            onChange={(text) => (search = text)}
            placeholder="Search logs"
            aria-label="Search logs"
            class="w-48"
          />
          <span class="ml-auto text-sm text-fg-muted tabular-nums">4 lines</span>
        </div>
        <div class="bottom-panel-box py-1.5 font-mono">
          {#each LOGS.filter((line) => line.text.toLowerCase().includes(search.toLowerCase())) as line (line.time)}
            <div class="flex gap-3 px-3 py-0.5">
              <span class="text-fg-faint tabular-nums">{line.time}</span>
              <span class={line.level === 'warning' ? 'text-warning-fg' : 'text-fg'}>{line.text}</span>
            </div>
          {/each}
        </div>
      </div>
    </section>
  </div>
</div>
