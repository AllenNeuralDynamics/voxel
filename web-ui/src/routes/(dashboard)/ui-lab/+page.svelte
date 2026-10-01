<script lang="ts">
  import Demo from './Demo.svelte';

  const textColors = [
    { token: 'fg', label: 'Primary text' },
    { token: 'fg-muted', label: 'Secondary text' },
    { token: 'fg-faint', label: 'Subtle text' },
    { token: 'fg-accent', label: 'Accent text' }
  ];
  const surfaces = ['canvas', 'surface', 'panel', 'elevated', 'floating'];
  const borders = [
    'line',
    'line-muted',
    'line-faint',
    'line-selected',
    'control-line',
    'control-line-hover',
    'border-focused',
    'border-disabled'
  ];
  const states = [
    { token: 'element-bg', label: 'Default' },
    { token: 'element-hover', label: 'Hover' },
    { token: 'element-active', label: 'Active' },
    { token: 'element-selected', label: 'Selected' }
  ];
  const textUsage = '<span class="text-fg">Primary text</span>\n<span class="text-fg-muted">Secondary text</span>';
  const typeUsage = '<span class="text-base">Label</span>\n<h2 class="text-lg font-medium">Section title</h2>';
  const borderUsage =
    '<div class="border border-line-muted">…</div>\n<button class="border border-control-line">…</button>';
</script>

<svelte:head><title>Appearance · UI Lab</title></svelte:head>

<h1 class="text-xl font-medium text-fg">Appearance</h1>
<div class="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(min(100%,24rem),1fr))] items-stretch gap-4">
  <Demo title="Text colors" usage={textUsage}>
    {#each textColors as { token, label } (token)}
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <span class="text-xl" style:color={`var(--${token})`}>{label}</span>
        <code class="text-base text-fg-muted">{token}</code>
      </div>
    {/each}
  </Demo>
  <Demo title="Type sizes" usage={typeUsage}>
    {#each ['text-base', 'text-lg', 'text-xl', 'text-2xl'] as size (size)}
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <span class={size}>Acquisition preview</span>
        <code class="text-base text-fg-muted">{size}</code>
      </div>
    {/each}
  </Demo>
  <Demo title="Surfaces" hint="Compare with the Background picker on the left.">
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {#each surfaces as token (token)}
        <div class="flex h-24 items-end rounded-md border border-line-muted p-3" style:background={`var(--${token})`}>
          <code class="text-base text-fg">{token}</code>
        </div>
      {/each}
    </div>
  </Demo>
  <Demo title="Interaction colors">
    <div class="grid grid-cols-2 gap-2">
      {#each states as { token, label } (token)}
        <div class="space-y-1 rounded-md p-3" style:background={`var(--${token})`}>
          <div class="text-lg">{label}</div>
          <code class="text-base text-fg-muted">{token}</code>
        </div>
      {/each}
    </div>
  </Demo>
  <Demo title="Borders" usage={borderUsage}>
    <div class="grid grid-cols-2 gap-2">
      {#each borders as token (token)}
        <div class="rounded-md border p-3" style:border-color={`var(--${token})`}>
          <code class="text-base text-fg-muted">{token}</code>
        </div>
      {/each}
    </div>
  </Demo>
  <Demo title="Status colors">
    <div class="grid grid-cols-2 gap-3">
      {#each ['danger', 'success', 'warning', 'info'] as token (token)}
        <div class="space-y-1">
          <div
            class="rounded-md px-3 py-2 text-base"
            style:background={`var(--${token})`}
            style:color={`var(--${token}-fg)`}
          >
            {token}
          </div>
          <div
            class="rounded-md px-3 py-2 text-base"
            style:background={`var(--${token}-bg)`}
            style:color={`var(--${token})`}
          >
            {token}-bg
          </div>
        </div>
      {/each}
    </div>
  </Demo>
</div>
