<script lang="ts">
  import { Button, NumberBox, Select, Switch, TextBox } from '@voxel/kit';
  import { Check, ChevronDown, CircleAlert, CircleCheck, Info, TriangleAlert } from '@voxel/kit/icons';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';

  let name = $state('Camera A');
  let exposure = $state(20);
  let binning = $state('2x2');
  let live = $state(true);
  let channel = $state(true);

  const BINNINGS = ['1x1', '2x2', '4x4'];
  const MENU = ['Fit to window', 'Zoom to 100%', 'Show grid', 'Reset view'];
  const IMAGE =
    'radial-gradient(circle at 28% 38%, var(--accent-muted), transparent 42%), radial-gradient(circle at 70% 64%, var(--success-muted), transparent 38%), var(--canvas)';
  const FRAMES = [
    'frame-raised',
    'frame-raised-link',
    'frame-floating',
    'frame-dialog',
    'frame-tinted',
    'frame-bordered',
    'frame-sunken',
    'frame-placeholder'
  ];
  const NOTES = [
    { name: 'note-accent', text: 'text-accent-fg' },
    { name: 'note-success', text: 'text-success-fg' },
    { name: 'note-warning', text: 'text-warning-fg' },
    { name: 'note-danger', text: 'text-danger-fg' }
  ];
  const MESSAGES = [
    { look: 'frame-tinted text-fg', icon: Info, text: 'Preview runs 2 of 4 channels.' },
    { look: 'note-success text-success-fg', icon: CircleCheck, text: 'brain-07 finished, 42 of 42 volumes.' },
    {
      look: 'note-warning text-warning-fg',
      icon: TriangleAlert,
      text: 'Filter wheel Emission is not at the profile filter.'
    },
    { look: 'note-danger text-danger-fg', icon: CircleAlert, text: 'The camera node stopped responding.' }
  ];
</script>

{#snippet tag(token: string, place = 'top-2 right-2.5')}
  <code class="pointer-events-none absolute font-mono text-xs text-fg-faint {place}">{token}</code>
{/snippet}

{#snippet modal(title: string, place: string)}
  <div class="relative h-80 overflow-hidden rounded-lg bg-pane ring-1 ring-line-faint ring-inset">
    <div class="m-4 h-20 frame-raised"></div>
    <div class="mx-4 h-10 w-1/2 frame-tinted"></div>
    <div class="absolute inset-0 bg-backdrop"></div>
    <div class="absolute flex flex-col gap-3 p-4 {place}">
      <span class="text-lg text-fg">{title}</span>
      <TextBox value={name} onChange={(text) => (name = text)} aria-label="Name, {title}" />
      <span class="flex items-center justify-between text-base text-fg-muted">
        Live
        <Switch size="lg" value={live} onChange={(on) => (live = on)} aria-label="Live, {title}" />
      </span>
      <div class="mt-auto flex justify-end gap-2">
        <Button variant="secondary">Cancel</Button>
        <Button>Save</Button>
      </div>
    </div>
  </div>
{/snippet}

<LabHeader title="Surfaces" />

<div class={lab.body}>
  <section class={lab.section}>
    <h2 class={lab.heading}>Shell</h2>
    <div
      class="relative grid h-[34rem] grid-cols-[3.25rem_19rem_minmax(0,1fr)_15rem] grid-rows-[2.75rem_minmax(0,1fr)] overflow-hidden frame-bordered"
    >
      <header class="relative col-span-4 flex items-center justify-end gap-2 border-b border-line-muted bg-shell px-3">
        <span class="flex h-ui-sm items-center gap-1 rounded-sm bg-element-selected px-2 text-sm text-fg">
          View <ChevronDown class="size-3" />
        </span>
        <span class="w-50"></span>
        {@render tag('shell', 'top-1/2 left-3 -translate-y-1/2')}
      </header>
      <nav
        class="relative flex flex-col items-center gap-2 border-r border-line-muted bg-shell py-3"
        aria-hidden="true"
      >
        {#each [0, 1, 2, 3] as index (index)}
          <span class={['size-7 rounded-lg', index === 1 ? 'bg-element-selected' : 'bg-tint']}></span>
        {/each}
      </nav>
      <section class="relative flex flex-col gap-3 border-r border-line-muted bg-pane p-3" aria-label="Pane">
        {@render tag('pane', 'bottom-2 left-3')}
        <div class="relative flex flex-col gap-2.5 frame-raised p-3">
          {@render tag('frame-raised')}
          <span class="text-base font-medium text-fg">Camera</span>
          <TextBox value={name} onChange={(text) => (name = text)} aria-label="Camera name" />
          <NumberBox value={exposure} onChange={(value) => (exposure = value)} min={0} prefix="Exposure" suffix="ms" />
          <Select
            size="lg"
            value={binning}
            options={BINNINGS}
            onChange={(next) => (binning = next)}
            aria-label="Binning"
          />
          <div class="relative flex flex-col frame-tinted px-2.5 py-2 text-sm">
            {@render tag('frame-tinted')}
            <span class="text-fg">2 channels are ready</span>
            <span class="text-fg-muted">1 camera is idle</span>
          </div>
        </div>
      </section>
      <div class="grid min-h-0 grid-rows-[minmax(0,1fr)_9rem]">
        <section class="relative" style:background={IMAGE} aria-label="Canvas">
          {@render tag('canvas', 'bottom-2 left-3')}
          <div class="absolute bottom-9 left-3 flex w-40 flex-col gap-1.5 frame-overlay p-2.5">
            {@render tag('overlay')}
            <span class="text-sm font-medium text-fg">Channels</span>
            <span class="flex items-center justify-between text-sm text-fg-muted">
              488 nm
              <Switch size="lg" value={channel} onChange={(on) => (channel = on)} aria-label="Show 488 nm" />
            </span>
          </div>
          <div class="absolute top-3 right-3 w-44 frame-floating p-1" aria-hidden="true">
            {#each MENU as item, index (item)}
              {#if index === 2}<div class="my-1 border-t border-line-faint"></div>{/if}
              <div
                class={[
                  'flex h-ui-sm items-center gap-2 rounded-sm px-2 text-sm',
                  index === 1 ? 'bg-element-hover text-fg' : 'text-fg-muted'
                ]}
              >
                <span class="flex size-3.5 items-center">
                  {#if item === 'Show grid'}<Check class="size-3.5" />{/if}
                </span>
                {item}
              </div>
            {/each}
            {@render tag('frame-floating', 'right-2.5 bottom-1.5')}
          </div>
        </section>
        <section class="relative flex flex-col border-t border-line-muted bg-pane" aria-label="Bottom pane">
          <div class="bottom-panel-bar text-sm text-fg-muted">Frames</div>
          <div class="bottom-panel-box"></div>
        </section>
      </div>
      <section class="relative bg-pane p-3" aria-label="Right pane">
        <div class="h-24 frame-raised"></div>
      </section>
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Frames</h2>
    <div class="grid grid-cols-5 gap-4">
      {#each FRAMES as look (look)}
        <div class="flex h-32 items-end p-3 {look}">
          <code class="font-mono text-sm text-fg">{look}</code>
        </div>
      {/each}
      <div class="relative flex h-32 items-end overflow-hidden rounded-lg p-3" style:background={IMAGE}>
        <div class="absolute inset-x-3 top-3 h-12 frame-overlay"></div>
        <code class="font-mono text-sm text-fg">frame-overlay</code>
      </div>
      <div class="relative flex h-32 items-end overflow-hidden rounded-lg p-3" style:background={IMAGE}>
        <span class="absolute top-4 left-4 flex items-center gap-1.5 text-sm text-fg halo">
          <span class="size-2 rounded-full bg-stage-mark"></span>488 nm
        </span>
        <code class="font-mono text-sm text-fg">halo</code>
      </div>
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Notes</h2>
    <div class="grid grid-cols-4 gap-4">
      {#each NOTES as note (note.name)}
        <div class="flex h-20 items-end p-3 {note.name}">
          <code class="font-mono text-sm {note.text}">{note.name}</code>
        </div>
      {/each}
    </div>
    <div class="grid grid-cols-2 gap-3">
      {#each MESSAGES as { look, icon: Icon, text } (text)}
        <p class="flex items-center gap-2 px-3 py-2.5 text-base {look}">
          <Icon class="size-4 shrink-0" aria-hidden="true" />{text}
        </p>
      {/each}
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Modals</h2>
    <div class="grid grid-cols-2 gap-4">
      {@render modal('Save preset', 'frame-dialog top-1/2 left-1/2 w-72 -translate-x-1/2 -translate-y-1/2')}
      {@render modal('Appearance', 'frame-dialog inset-y-0 right-0 w-72 rounded-none')}
    </div>
  </section>
</div>
