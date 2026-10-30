<script lang="ts">
  import { NumberBox, TextBox } from '$lib/kit';
  import { CircleAlert } from '$lib/kit/icons';

  import { lab } from './lab';
  import LabHeader from './LabHeader.svelte';

  const LAYERS = [
    { name: 'canvas', look: 'bg-canvas' },
    { name: 'pane', look: 'bg-pane' },
    { name: 'shell', look: 'bg-shell' },
    { name: 'raised', look: 'frame-raised' },
    { name: 'floating', look: 'frame-floating' }
  ];
  const FILL_LOOKS = [
    { name: 'element-bg', look: 'bg-element-bg' },
    { name: 'element-hover', look: 'bg-element-hover' },
    { name: 'element-selected', look: 'bg-element-selected' },
    { name: 'element-active', look: 'bg-element-active' }
  ];
  const WASHES = [
    { name: 'tint', look: 'frame-tinted hover:bg-tint-hover' },
    { name: 'tint-hover', look: 'rounded-md bg-tint-hover' },
    { name: 'element-hover', look: 'rounded-md bg-element-hover' }
  ];

  const SOLID = ['canvas', 'pane', 'shell', 'raised', 'floating'];
  const CLEAR = ['tint', 'tint-hover', 'overlay', 'backdrop'];
  const TEXT = [
    { token: 'fg', sample: 'Acquisition preview at 488 nm' },
    { token: 'fg-muted', sample: 'Exposure time' },
    { token: 'fg-faint', sample: 'Saved 2 min ago' },
    { token: 'accent-fg', sample: 'Open the log' }
  ];
  const RULES = ['line', 'line-muted', 'line-faint', 'line-selected'];
  const FILLS = ['element-bg', 'element-hover', 'element-selected', 'element-active', 'track'];
  const FAMILIES = ['accent', 'danger', 'warning', 'success'];
  const SERIES = ['series-1', 'series-2', 'series-3', 'series-4', 'stage-mark'];
  const AXES = ['x', 'y', 'z'];

  let search = $state('');
  let gain = $state(2);
</script>

{#snippet row(name: string, look: string, cells: import('svelte').Snippet)}
  <div class="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-4 p-3 {look}">
    <code class={lab.code}>{name}</code>
    {@render cells()}
  </div>
{/snippet}

<LabHeader title="Color" />

<div class={lab.body}>
  <section class={lab.section}>
    <h2 class={lab.heading}>Layers</h2>
    <div class="grid grid-cols-5 gap-x-3 gap-y-5">
      {#each SOLID as token (token)}
        <figure class="flex flex-col gap-2">
          <div class="h-28 rounded-lg ring-1 ring-line-faint ring-inset" style:background={`var(--${token})`}></div>
          <figcaption class={lab.code}>--{token}</figcaption>
        </figure>
      {/each}
      {#each CLEAR as token (token)}
        <figure class="flex flex-col gap-2">
          <div
            class="relative h-28 overflow-hidden rounded-lg ring-1 ring-line-faint ring-inset"
            style:background="linear-gradient(90deg, var(--canvas) 50%, var(--raised) 50%)"
          >
            <div class="absolute inset-4 rounded-md" style:background={`var(--${token})`}></div>
          </div>
          <figcaption class={lab.code}>--{token}</figcaption>
        </figure>
      {/each}
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Text and boxes on each layer</h2>
    <div class="flex flex-col gap-2 rounded-lg bg-pane p-2 ring-1 ring-line-faint">
      {#each LAYERS as layer (layer.name)}
        {#snippet cells()}
          <div
            class="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_11rem_9rem_minmax(0,1.2fr)] items-center gap-4 text-base"
          >
            <span class="flex items-baseline justify-between gap-2">
              <span class="text-fg-muted">Exposure</span><span class="text-fg tabular-nums">20 ms</span>
            </span>
            <span class="text-fg-faint">Saved 2 min ago</span>
            <TextBox
              value={search}
              onChange={(text) => (search = text)}
              placeholder="Search"
              aria-label="Search, {layer.name}"
            />
            <NumberBox
              value={gain}
              onChange={(value) => (gain = value)}
              min={0}
              prefix="Gain"
              aria-label="Gain, {layer.name}"
            />
            <span class="flex flex-col frame-tinted px-2.5 py-1 text-sm">
              <span class="text-fg">2 channels are ready</span>
              <span class="text-fg-muted">1 camera is idle</span>
            </span>
          </div>
        {/snippet}
        {@render row(layer.name, layer.look, cells)}
      {/each}
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Washes</h2>
    <div class="flex flex-col gap-2 rounded-lg bg-pane p-2 ring-1 ring-line-faint">
      <div class="grid grid-cols-[7rem_minmax(0,1fr)] gap-4 px-3">
        <span></span>
        <div class="grid grid-cols-3 gap-2">
          {#each WASHES as wash (wash.name)}<code class={lab.code}>{wash.name}</code>{/each}
        </div>
      </div>
      {#each LAYERS as layer (layer.name)}
        {#snippet cells()}
          <div class="grid grid-cols-3 gap-2">
            {#each WASHES as wash (wash.name)}
              <div class="flex h-ui-sm items-center px-2 text-sm text-fg transition-colors {wash.look}">2 channels</div>
            {/each}
          </div>
        {/snippet}
        {@render row(layer.name, layer.look, cells)}
      {/each}
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Text</h2>
    <div class="frame-raised px-3 py-1">
      <table class={lab.table}>
        <tbody class={lab.tbody}>
          {#each TEXT as { token, sample } (token)}
            <tr>
              <td class="{lab.td} w-48"><code class={lab.code}>--{token}</code></td>
              <td class="{lab.td} text-xl" style:color={`var(--${token})`}>{sample}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Lines</h2>
    <div class="frame-raised px-3 py-1">
      <table class={lab.table}>
        <tbody class={lab.tbody}>
          {#each RULES as token (token)}
            <tr>
              <td class="{lab.td} w-48"><code class={lab.code}>--{token}</code></td>
              <td class={lab.td}><div class="h-px" style:background={`var(--${token})`}></div></td>
            </tr>
          {/each}
          <tr>
            <td class="{lab.td} w-48"><code class={lab.code}>--control-line</code></td>
            <td class={lab.td}><div class="h-ui-sm w-48 rounded-sm border border-control-line bg-element-bg"></div></td>
          </tr>
          <tr>
            <td class="{lab.td} w-48"><code class={lab.code}>--control-line-hover</code></td>
            <td class={lab.td}>
              <div class="h-ui-sm w-48 rounded-sm border border-control-line-hover bg-element-hover"></div>
            </td>
          </tr>
          <tr>
            <td class="{lab.td} w-48"><code class={lab.code}>--focus</code></td>
            <td class={lab.td}>
              <div
                class="h-ui-sm w-48 rounded-sm border border-control-line bg-element-bg outline-2 outline-offset-2 outline-focus"
              ></div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Control fills</h2>
    <div class="grid grid-cols-5 gap-3">
      {#each FILLS as token (token)}
        <figure class="flex flex-col gap-2">
          <div class="h-ui-lg rounded-md" style:background={`var(--${token})`}></div>
          <figcaption class={lab.code}>--{token}</figcaption>
        </figure>
      {/each}
    </div>
    <div class="flex flex-col gap-2 rounded-lg bg-pane p-2 ring-1 ring-line-faint">
      <div class="grid grid-cols-[7rem_minmax(0,1fr)] gap-4 px-3">
        <span></span>
        <div class="grid grid-cols-4 gap-2">
          {#each FILL_LOOKS as fill (fill.name)}<code class={lab.code}>{fill.name}</code>{/each}
        </div>
      </div>
      {#each LAYERS as layer (layer.name)}
        {#snippet cells()}
          <div class="grid grid-cols-4 gap-2">
            {#each FILL_LOOKS as fill (fill.name)}<div class="h-ui-sm rounded-sm {fill.look}"></div>{/each}
          </div>
        {/snippet}
        {@render row(layer.name, layer.look, cells)}
      {/each}
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Families</h2>
    <div class="frame-raised px-3 py-1">
      <table class={lab.table}>
        <thead class={lab.thead}>
          <tr>
            <th class="{lab.th} w-32"></th>
            {#each ['X, on-X', 'X-hover', 'X-muted', 'X-tint', 'X-fg'] as heading (heading)}
              <th class="{lab.th} font-mono">{heading}</th>
            {/each}
          </tr>
        </thead>
        <tbody class={lab.tbody}>
          {#each FAMILIES as family (family)}
            <tr>
              <th scope="row" class="{lab.td} text-base font-normal text-fg capitalize">{family}</th>
              <td class={lab.td}>
                <span
                  class="inline-flex h-ui-sm items-center rounded-sm px-2.5 text-base font-medium"
                  style:background={`var(--${family})`}
                  style:color={`var(--on-${family})`}>Aa</span
                >
              </td>
              <td class={lab.td}>
                <span
                  class="inline-flex h-ui-sm items-center rounded-sm px-2.5 text-base font-medium"
                  style:background={`var(--${family}-hover)`}
                  style:color={`var(--on-${family})`}>Aa</span
                >
              </td>
              <td class={lab.td}>
                <span class="block h-1.5 w-24 overflow-hidden rounded-full bg-track">
                  <span class="block h-full w-2/3 rounded-full" style:background={`var(--${family}-muted)`}></span>
                </span>
              </td>
              <td class={lab.td}>
                <span
                  class="inline-flex h-ui-sm items-center gap-1.5 rounded-sm border px-2 text-sm"
                  style:background={`var(--${family}-tint)`}
                  style:border-color={`var(--${family}-muted)`}
                  style:color={`var(--${family}-fg)`}
                >
                  <CircleAlert class="size-3.5" />Note
                </span>
              </td>
              <td class={lab.td}>
                <span class="inline-flex items-center gap-1.5 text-base" style:color={`var(--${family}-fg)`}>
                  <span class="size-2 rounded-full bg-current"></span>Ready
                </span>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <code class="px-1 {lab.code}">on frame-floating</code>
    <div class="grid grid-cols-4 gap-3 frame-floating p-4">
      {#each FAMILIES as family (family)}
        <div class="flex flex-col gap-2.5">
          <span class="flex items-center gap-2 text-base" style:color={`var(--${family}-fg)`}>
            <span class="size-2 rounded-full bg-current"></span>
            <CircleAlert class="size-3.5" />
            <span class="capitalize">{family}</span>
          </span>
          <span
            class="flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm"
            style:background={`var(--${family}-tint)`}
            style:border-color={`var(--${family}-muted)`}
            style:color={`var(--${family}-fg)`}
          >
            <CircleAlert class="size-3.5" />Note
          </span>
        </div>
      {/each}
    </div>
  </section>

  <section class={lab.section}>
    <h2 class={lab.heading}>Data</h2>
    <div class="grid grid-cols-5 gap-3">
      {#each SERIES as token (token)}
        <figure class="flex flex-col gap-2">
          <div class="h-ui-lg rounded-md" style:background={`var(--${token})`}></div>
          <figcaption class={lab.code}>--{token}</figcaption>
        </figure>
      {/each}
      {#each AXES as axis (axis)}
        <figure class="flex flex-col gap-2">
          <div
            class="flex h-ui-lg items-center justify-center rounded-md text-lg font-medium uppercase"
            style:background={`var(--axis-${axis}-tint)`}
            style:color={`var(--axis-${axis})`}
          >
            {axis}
          </div>
          <figcaption class={lab.code}>--axis-{axis}</figcaption>
        </figure>
      {/each}
    </div>
  </section>
</div>
