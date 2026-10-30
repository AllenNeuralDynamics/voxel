<script lang="ts">
  import { resolve } from '$app/paths';
  import { cn } from '$lib/core/utils';
  import { LEVEL_DOT } from '$lib/features/issues';
  import { Badge, Button, CollapsibleSection, NumberBox, RadioBar, Section, Select, Switch, TextBox } from '$lib/kit';
  import { ArrowRight, Plus, RefreshCw, Trash } from '$lib/kit/icons';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';

  type Look = 'plain' | 'raised' | 'bordered';
  type Content = 'settings' | 'controls' | 'devices' | 'prose' | 'empty';

  const LOOKS: readonly Look[] = ['plain', 'raised', 'bordered'];
  /** The content pane's usual width, so each example has the shape it has in the app. */
  const PANE = 'w-98 shrink-0';
  const LEVELS: readonly { name: string; look: string; title: string; content: Content }[] = [
    { name: 'canvas', look: 'bg-canvas', title: 'Camera', content: 'settings' },
    { name: 'pane', look: 'bg-pane', title: 'Acquisition', content: 'controls' },
    { name: 'shell', look: 'bg-shell', title: 'Node 1', content: 'devices' },
    { name: 'raised', look: 'frame-raised', title: 'About this profile', content: 'prose' },
    { name: 'floating', look: 'frame-floating', title: 'Volumes', content: 'empty' }
  ];
  const SETTINGS = [
    ['Exposure', '10 ms'],
    ['Binning', '1×1'],
    ['Gain', '2'],
    ['Pixel format', 'Mono16'],
    ['Trigger', 'Internal']
  ];
  const DEVICES = [
    { name: 'Camera 1', role: 'Camera', reading: '24 fps, 410 MB/s', ok: true },
    { name: 'Laser 488', role: 'Laser', reading: '12 mW', ok: true },
    { name: 'Filter wheel', role: 'Filter wheel', reading: 'Slot 3', ok: true },
    { name: 'Stage X', role: 'Stage', reading: 'Not connected', ok: false }
  ];
  const here = resolve('/(dashboard)/ui-lab/sections');
  const LASERS = [
    { name: 'Laser 405', role: '405 nm, DAPI', reading: '12.0 mW', changed: false, issue: null },
    { name: 'Laser 488', role: '488 nm, GFP', reading: '20.0 mW', changed: true, issue: null },
    { name: 'Laser 561', role: '561 nm, RFP', reading: 'Off', changed: false, issue: 'warning' },
    { name: 'Laser 640', role: '640 nm, Cy5', reading: '—', changed: false, issue: 'error' }
  ] as const;
  const POSITIONS = ['Tile A1 · 0, 0 µm', 'Tile A2 · 1,200, 0 µm', 'Tile B1 · 0, 1,200 µm'];
  const SAVED = [
    { device: 'Camera 1', setting: 'Binning', value: '1' },
    { device: 'Camera 1', setting: 'Exposure', value: '10 ms' },
    { device: 'Laser 488', setting: 'Power', value: '12 mW' },
    { device: 'Filter wheel', setting: 'Position', value: 'GFP' }
  ];
  const CONFIG = `instrument: simulated-distributed
detection:
  camera_1:
    filter_wheels: [fw_emission_cam1]
illumination:
  laser_488: {}`;

  let exposure = $state(10);
  let binning = $state('1×1');
  let live = $state(true);
  let label = $state('Overnight run');
  let destinationOpen = $state(false);

  const TH = 'h-9 px-2.5 text-sm font-normal whitespace-nowrap text-fg-muted';

  // Playground
  type Kind = 'Section' | 'CollapsibleSection';
  type HeadingKind = 'short' | 'long' | 'rich' | 'link';
  type TrailingKind = 'none' | 'text' | 'actions';
  type Edge = 'none' | 'top' | 'right' | 'bottom' | 'left';
  type Width = 'narrow' | 'pane' | 'wide';
  type Level = 'canvas' | 'pane' | 'shell' | 'raised' | 'floating';
  type PlayContent = Content | 'table' | 'code';

  const DOCKED: Record<Edge, string> = {
    none: '',
    top: 'frame-docked-top',
    right: 'frame-docked-right',
    bottom: 'frame-docked-bottom',
    left: 'frame-docked-left'
  };
  const WIDTHS: Record<Width, string> = { narrow: 'w-70', pane: 'w-98', wide: 'w-160' };
  const BACKGROUNDS: Record<Level, string> = {
    canvas: 'bg-canvas',
    pane: 'bg-pane',
    shell: 'bg-shell',
    raised: 'frame-raised',
    floating: 'frame-floating'
  };
  const LONG_HEADING = 'Saved positions for the overnight tiling run';

  interface PlayState {
    variant: Look;
    headingKind: HeadingKind;
    trailingKind: TrailingKind;
    flush: boolean;
    open: boolean;
    edge: Edge;
    content: PlayContent;
    width: Width;
    level: Level;
  }

  const START: PlayState = {
    variant: 'raised',
    headingKind: 'short',
    trailingKind: 'text',
    flush: false,
    open: true,
    edge: 'none',
    content: 'settings',
    width: 'pane',
    level: 'pane'
  };
  const sectionPlay = $state<PlayState>({ ...START });
  const collapsiblePlay = $state<PlayState>({ ...START });

  function headingFor(play: PlayState) {
    if (play.headingKind === 'short') return 'Camera';
    if (play.headingKind === 'long') return LONG_HEADING;
    return play.headingKind === 'rich' ? richHeading : deviceLink;
  }

  function trailingFor(play: PlayState) {
    if (play.trailingKind === 'text') return trailingText;
    return play.trailingKind === 'actions' ? positionActions : undefined;
  }

  function codeFor(tag: Kind, play: PlayState) {
    const parts = [
      play.headingKind === 'short'
        ? 'heading="Camera"'
        : play.headingKind === 'long'
          ? `heading="${LONG_HEADING}"`
          : 'heading={snippet}'
    ];
    if (play.variant !== (tag === 'Section' ? 'plain' : 'raised')) parts.push(`variant="${play.variant}"`);
    if (play.trailingKind !== 'none') parts.push('trailing={snippet}');
    if (play.flush) parts.push('flush');
    if (tag === 'CollapsibleSection') parts.push('bind:open');
    if (play.edge !== 'none') parts.push(`class="${DOCKED[play.edge]}"`);
    return `<${tag} ${parts.join(' ')}>`;
  }
</script>

{#snippet settings(look: Look, rows = SETTINGS)}
  <dl class={['grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-base', look === 'plain' && 'px-2.5']}>
    {#each rows as [name, value] (name)}
      <dt class="text-fg-muted">{name}</dt>
      <dd class="text-fg tabular-nums">{value}</dd>
    {/each}
  </dl>
{/snippet}

{#snippet controls(look: Look)}
  <div
    class={['grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-x-3 gap-y-2 text-base', look === 'plain' && 'px-2.5']}
  >
    <span class="text-fg-muted">Exposure</span>
    <NumberBox
      value={exposure}
      onChange={(next) => (exposure = next)}
      min={0}
      step={0.1}
      suffix="ms"
      aria-label="Exposure"
    />
    <span class="text-fg-muted">Binning</span>
    <RadioBar
      size="lg"
      value={binning}
      options={['1×1', '2×2', '4×4']}
      onChange={(next) => (binning = next)}
      aria-label="Binning"
    />
    <span class="text-fg-muted">Live</span>
    <Switch size="lg" value={live} onChange={(on) => (live = on)} aria-label="Live" />
    <span class="text-fg-muted">Label</span>
    <TextBox value={label} onChange={(next) => (label = next)} aria-label="Label" />
  </div>
{/snippet}

{#snippet devices(look: Look)}
  <ul class="divide-y divide-line-faint">
    {#each DEVICES as device (device.name)}
      <li class={['flex items-center gap-2 py-1.5 text-base', look === 'plain' && 'px-2.5']}>
        <span class={['size-2 shrink-0 rounded-full', device.ok ? 'bg-success' : 'bg-danger']} aria-hidden="true"
        ></span>
        <span class="text-fg">{device.name}</span>
        <span class="text-fg-muted">{device.role}</span>
        <span class="ml-auto text-fg-muted tabular-nums">{device.reading}</span>
      </li>
    {/each}
  </ul>
{/snippet}

{#snippet prose(look: Look)}
  <div class={['flex flex-col items-start gap-2 text-base text-fg-muted', look === 'plain' && 'px-2.5']}>
    <p>
      DAPI and Cy5 share camera 1. The profile saves the exposure and binning of the camera, and the power of each
      laser, and sets them again when you choose it.
    </p>
    <Button variant="secondary">Edit profile</Button>
  </div>
{/snippet}

{#snippet empty(look: Look)}
  <div class={['flex flex-col items-center gap-2 py-4 text-base text-fg-muted', look === 'plain' && 'px-2.5']}>
    <p>No volumes yet.</p>
    <Button variant="secondary"><Plus /> Add volume</Button>
  </div>
{/snippet}

{#snippet content(kind: Content, look: Look)}
  {#if kind === 'settings'}
    {@render settings(look)}
  {:else if kind === 'controls'}
    {@render controls(look)}
  {:else if kind === 'devices'}
    {@render devices(look)}
  {:else if kind === 'prose'}
    {@render prose(look)}
  {:else}
    {@render empty(look)}
  {/if}
{/snippet}

{#snippet reset()}
  <Button variant="quiet">Reset</Button>
{/snippet}

{#snippet positionActions()}
  <Badge>{POSITIONS.length}</Badge>
  <Button variant="ghost" size="icon-sm" aria-label="Refresh"><RefreshCw /></Button>
  <Button variant="ghost" size="icon-sm" aria-label="Delete all"><Trash /></Button>
{/snippet}

{#snippet positions(look: Look)}
  <ul class="divide-y divide-line-faint">
    {#each POSITIONS as position (position)}
      <li class={['py-1.5 text-base text-fg tabular-nums', look === 'plain' && 'px-2.5']}>{position}</li>
    {/each}
  </ul>
{/snippet}

{#snippet deviceLink()}
  <a href="#cases-heading" class="inline-flex items-center gap-2 rounded-sm hover:underline">
    <span class="size-2 shrink-0 rounded-full bg-success" aria-hidden="true"></span>
    Camera 1
  </a>
{/snippet}

{#snippet table()}
  <table class={lab.table}>
    <thead class={lab.thead}>
      <tr>
        <th class={TH}>Device</th>
        <th class={TH}>Setting</th>
        <th class="{TH} text-right">Value</th>
      </tr>
    </thead>
    <tbody class={lab.tbody}>
      {#each SAVED as row (row.device + row.setting)}
        <tr>
          <td class="px-2.5 py-2 text-fg">{row.device}</td>
          <td class="px-2.5 py-2 text-fg-muted">{row.setting}</td>
          <td class="px-2.5 py-2 text-right text-fg tabular-nums">{row.value}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/snippet}

{#snippet code()}
  <pre class="overflow-x-auto p-2.5 font-mono text-sm text-fg">{CONFIG}</pre>
{/snippet}

{#snippet labeled(look: Look, body: import('svelte').Snippet)}
  <div class="flex {PANE} flex-col gap-1.5">
    <code class={lab.code}>variant="{look}"</code>
    {@render body()}
  </div>
{/snippet}

{#snippet richHeading()}
  <span class="inline-flex items-center gap-2">
    <span class="size-2 shrink-0 rounded-full bg-success" aria-hidden="true"></span>
    Camera 1
  </span>
{/snippet}

{#snippet trailingText()}
  <span class="truncate text-sm text-fg-muted">3 of 4</span>
{/snippet}

{#snippet playBody(play: PlayState)}
  {#if play.content === 'table'}
    {@render table()}
  {:else if play.content === 'code'}
    {@render code()}
  {:else}
    {@render content(play.content, play.variant)}
  {/if}
{/snippet}

{#snippet playground(tag: Kind, play: PlayState)}
  <div class="flex flex-wrap items-stretch gap-6">
    <dl
      class="grid w-100 shrink-0 grid-cols-[6rem_minmax(0,1fr)] content-start items-center gap-x-2.5 gap-y-1.5 frame-raised p-2.5"
    >
      <dt class="text-sm text-fg-muted">Variant</dt>
      <dd>
        <RadioBar
          value={play.variant}
          options={tag === 'Section' ? LOOKS : (['raised', 'bordered'] as const)}
          onChange={(next) => (play.variant = next)}
          class="w-full"
          aria-label="Variant"
        />
      </dd>
      <dt class="text-sm text-fg-muted">Heading</dt>
      <dd>
        <RadioBar
          value={play.headingKind}
          options={['short', 'long', 'rich', 'link'] as const}
          onChange={(next) => (play.headingKind = next)}
          class="w-full"
          aria-label="Heading"
        />
      </dd>
      <dt class="text-sm text-fg-muted">Trailing</dt>
      <dd>
        <RadioBar
          value={play.trailingKind}
          options={['none', 'text', 'actions'] as const}
          onChange={(next) => (play.trailingKind = next)}
          class="w-full"
          aria-label="Trailing"
        />
      </dd>
      <dt class="text-sm text-fg-muted">Flush</dt>
      <dd class="flex h-ui-sm items-center">
        <Switch value={play.flush} onChange={(on) => (play.flush = on)} aria-label="Flush" />
      </dd>
      {#if tag === 'CollapsibleSection'}
        <dt class="text-sm text-fg-muted">Open</dt>
        <dd class="flex h-ui-sm items-center">
          <Switch value={play.open} onChange={(on) => (play.open = on)} aria-label="Open" />
        </dd>
      {/if}
      <dt class="text-sm text-fg-muted">Docked</dt>
      <dd>
        <Select
          value={play.edge}
          options={['none', 'top', 'right', 'bottom', 'left'] as const}
          onChange={(next) => (play.edge = next)}
          class="w-full"
          aria-label="Docked"
        />
      </dd>
      <dt class="text-sm text-fg-muted">Content</dt>
      <dd>
        <Select
          value={play.content}
          options={['settings', 'controls', 'devices', 'prose', 'empty', 'table', 'code'] as const}
          onChange={(next) => (play.content = next)}
          class="w-full"
          aria-label="Content"
        />
      </dd>
      <dt class="text-sm text-fg-muted">Width</dt>
      <dd>
        <RadioBar
          value={play.width}
          options={['narrow', 'pane', 'wide'] as const}
          onChange={(next) => (play.width = next)}
          class="w-full"
          aria-label="Width"
        />
      </dd>
      <dt class="text-sm text-fg-muted">Background</dt>
      <dd>
        <Select
          value={play.level}
          options={['canvas', 'pane', 'shell', 'raised', 'floating'] as const}
          onChange={(next) => (play.level = next)}
          class="w-full"
          aria-label="Background"
        />
      </dd>
    </dl>
    <div class="flex min-w-0 flex-1 flex-col gap-6 p-6 {BACKGROUNDS[play.level]}">
      <div class="flex flex-1 items-start">
        <div class={WIDTHS[play.width]}>
          {#if tag === 'CollapsibleSection'}
            <CollapsibleSection
              heading={headingFor(play)}
              variant={play.variant === 'plain' ? 'raised' : play.variant}
              trailing={trailingFor(play)}
              flush={play.flush}
              bind:open={() => play.open, (open) => (play.open = open)}
              class={DOCKED[play.edge]}
            >
              {@render playBody(play)}
            </CollapsibleSection>
          {:else}
            <Section
              heading={headingFor(play)}
              variant={play.variant}
              trailing={trailingFor(play)}
              flush={play.flush}
              class={DOCKED[play.edge]}
            >
              {@render playBody(play)}
            </Section>
          {/if}
        </div>
      </div>
      <pre class="overflow-x-auto frame-sunken p-2.5 font-mono text-sm text-fg">{codeFor(tag, play)}</pre>
    </div>
  </div>
{/snippet}

<LabHeader title="Sections" />

<div class={cn(lab.body, 'max-w-none')}>
  <section class={lab.section} aria-labelledby="list-heading">
    <h2 id="list-heading" class={lab.heading}>Section and list</h2>
    <div class={PANE}>
      <Section heading="Lasers">
        {#snippet trailing()}
          <span class="flex items-baseline gap-2">
            <Badge tone="danger">1 error</Badge>
            <a href={here} class="flex items-center gap-1 rounded-sm text-sm text-fg-muted hover:text-fg"
              >Controls<ArrowRight class="size-3" aria-hidden="true" /></a
            >
          </span>
        {/snippet}
        <ul class="flex min-w-0 flex-col divide-y divide-line-faint frame-raised p-1">
          {#each LASERS as laser (laser.name)}
            <li class="mx-2">
              <a
                href={here}
                class="-mx-2 flex min-w-0 flex-col gap-0.5 rounded-md px-2 py-3 transition-colors hover:bg-element-hover"
              >
                <span class="flex min-w-0 items-center gap-2">
                  <span class="min-w-0 flex-1 truncate text-base font-medium text-fg">{laser.name}</span>
                  <span class="text-sm text-fg-muted tabular-nums">{laser.reading}</span>
                </span>
                <span class="flex min-w-0 items-center gap-2">
                  <span class="min-w-0 flex-1 truncate text-sm text-fg-muted">{laser.role}</span>
                  {#if laser.changed}<span class="size-1.5 shrink-0 rounded-full bg-accent-fg"></span>{/if}
                  {#if laser.issue}<span class="size-2 shrink-0 rounded-full {LEVEL_DOT[laser.issue]}"></span>{/if}
                </span>
              </a>
            </li>
          {/each}
        </ul>
      </Section>
    </div>
  </section>

  <section class={lab.section} aria-labelledby="playground-heading">
    <h2 id="playground-heading" class={lab.heading}>Section playground</h2>
    {@render playground('Section', sectionPlay)}
  </section>

  <section class={lab.section} aria-labelledby="levels-heading">
    <h2 id="levels-heading" class={lab.heading}>Each look on each background level</h2>
    {#each LEVELS as level (level.name)}
      <div class="flex flex-col gap-1.5">
        <code class="px-1 {lab.code}">{level.name}</code>
        <div class="flex flex-wrap items-start gap-6 p-4 {level.look}">
          {#each LOOKS as look (look)}
            {#snippet example()}
              <Section heading={level.title} variant={look} trailing={reset}>
                {@render content(level.content, look)}
              </Section>
            {/snippet}
            {@render labeled(look, example)}
          {/each}
        </div>
      </div>
    {/each}
  </section>

  <section class={lab.section} aria-labelledby="cases-heading">
    <h2 id="cases-heading" class={lab.heading}>Each option in each look, on the pane</h2>

    <code class="px-1 {lab.code}">heading="Camera"</code>
    <div class="flex flex-wrap items-start gap-6 px-4">
      {#each LOOKS as look (look)}
        {#snippet example()}
          <Section heading="Camera" variant={look}>{@render settings(look, SETTINGS.slice(0, 3))}</Section>
        {/snippet}
        {@render labeled(look, example)}
      {/each}
    </div>

    <code class="px-1 {lab.code}">trailing=&#123;…&#125;, with a long title</code>
    <div class="flex flex-wrap items-start gap-6 px-4">
      {#each LOOKS as look (look)}
        {#snippet example()}
          <Section heading="Saved positions for the overnight tiling run" variant={look} trailing={positionActions}>
            {@render positions(look)}
          </Section>
        {/snippet}
        {@render labeled(look, example)}
      {/each}
    </div>

    <code class="px-1 {lab.code}">heading=&#123;snippet&#125;</code>
    <div class="flex flex-wrap items-start gap-6 px-4">
      {#each LOOKS as look (look)}
        {#snippet example()}
          <Section heading={deviceLink} variant={look}>{@render controls(look)}</Section>
        {/snippet}
        {@render labeled(look, example)}
      {/each}
    </div>

    <code class="px-1 {lab.code}">flush, with a table</code>
    <div class="flex flex-wrap items-start gap-6 px-4">
      {#each LOOKS as look (look)}
        {#snippet example()}
          <Section heading="Saved device values" variant={look} flush>{@render table()}</Section>
        {/snippet}
        {@render labeled(look, example)}
      {/each}
    </div>

    <code class="px-1 {lab.code}">flush, with code</code>
    <div class="flex flex-wrap items-start gap-6 px-4">
      {#each LOOKS as look (look)}
        {#snippet example()}
          <Section heading="config.yaml" variant={look} flush>{@render code()}</Section>
        {/snippet}
        {@render labeled(look, example)}
      {/each}
    </div>
  </section>

  <section class={lab.section} aria-labelledby="collapsible-heading">
    <h2 id="collapsible-heading" class={lab.heading}>CollapsibleSection playground</h2>
    {@render playground('CollapsibleSection', collapsiblePlay)}

    <h3 class="px-1 text-sm text-fg-muted">CollapsibleSection, on the pane</h3>

    <code class="px-1 {lab.code}">closed, with trailing text</code>
    <div class="flex flex-wrap items-start gap-6 px-4">
      {#each ['raised', 'bordered'] as const as variant (variant)}
        {#snippet example()}
          <CollapsibleSection heading="Destination" {variant}>
            {#snippet trailing()}<span class="truncate text-sm text-fg-muted">Local</span>{/snippet}
            {@render settings('raised')}
          </CollapsibleSection>
        {/snippet}
        {@render labeled(variant, example)}
      {/each}
    </div>

    <code class="px-1 {lab.code}">open</code>
    <div class="flex flex-wrap items-start gap-6 px-4">
      {#each ['raised', 'bordered'] as const as variant (variant)}
        {#snippet example()}
          <CollapsibleSection heading="Sample" {variant} open>
            {#snippet trailing()}<span class="truncate text-sm text-danger-fg">Operator is empty</span>{/snippet}
            {@render controls('raised')}
          </CollapsibleSection>
        {/snippet}
        {@render labeled(variant, example)}
      {/each}
    </div>

    <code class="px-1 {lab.code}">bind:open, opened from outside</code>
    <div class="flex flex-wrap items-start gap-6 px-4">
      {#snippet example()}
        <CollapsibleSection heading="Destination" bind:open={destinationOpen}>
          {@render settings('raised')}
        </CollapsibleSection>
      {/snippet}
      {@render labeled('raised', example)}
      <Button variant="secondary" onclick={() => (destinationOpen = !destinationOpen)}>
        {destinationOpen ? 'Close' : 'Open'} from outside
      </Button>
    </div>
  </section>
</div>
