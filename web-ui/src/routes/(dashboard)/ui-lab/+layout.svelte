<script lang="ts">
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { ThemePicker } from '$lib/themes';

  const { children } = $props();
  const surfaces = [
    { name: 'Canvas', bg: 'bg-canvas' },
    { name: 'Surface', bg: 'bg-surface' },
    { name: 'Elevated', bg: 'bg-elevated' }
  ];
  let activeSurface = $state(0);
  const sections = [
    { label: 'Appearance', route: '/(dashboard)/ui-lab' },
    { label: 'Buttons & inputs', route: '/(dashboard)/ui-lab/buttons-inputs' },
    { label: 'Property editors', route: '/(dashboard)/ui-lab/property-editors' },
    { label: 'Sortable', route: '/(dashboard)/ui-lab/sortable' },
    { label: 'Scroll area', route: '/(dashboard)/ui-lab/scroll-area' }
  ] as const;
</script>

<div class="grid h-full min-h-0 grid-cols-[auto_minmax(0,1fr)]">
  <section class="flex min-h-0 flex-col gap-4 overflow-auto bg-panel p-4">
    <ThemePicker />

    <div class="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-4">
      <span class="text-base text-fg">Background</span>
      <div class="grid min-w-0 grid-cols-3 gap-1" role="group" aria-label="Preview background">
        {#each surfaces as { name }, i (i)}
          <button
            class="h-ui-sm min-w-0 cursor-pointer rounded-md border px-2 text-base transition-colors hover:bg-element-hover {activeSurface ===
            i
              ? 'border-primary bg-primary/10 text-primary'
              : 'border-control-line text-fg-muted hover:border-control-line-hover hover:text-fg'}"
            aria-pressed={activeSurface === i}
            onclick={() => (activeSurface = i)}
          >
            {name}
          </button>
        {/each}
      </div>
    </div>

    <nav class="space-y-2 border-t border-line-muted pt-4" aria-label="UI Lab navigation">
      <h2 class="text-base text-fg-muted">UI Lab</h2>
      <div class="flex flex-col gap-1">
        {#each sections as section (section.route)}
          {@const selected = page.route.id === section.route}
          <a
            href={resolve(section.route)}
            class="min-h-ui-md rounded-md border px-3 py-1.5 text-left text-lg transition-colors hover:bg-element-hover focus-visible:outline-2 focus-visible:outline-border-focused {selected
              ? 'border-primary bg-primary/10 text-primary'
              : 'border-control-line text-fg-muted hover:border-control-line-hover hover:text-fg'}"
            aria-current={selected ? 'page' : undefined}
          >
            {section.label}
          </a>
        {/each}
      </div>
    </nav>
  </section>
  <section class="h-full min-h-0 min-w-0 overflow-hidden p-4">
    {#key page.route.id}
      <div
        class="h-full min-h-0 overflow-auto rounded-lg border border-line-muted {surfaces[activeSurface]
          .bg} flex flex-col gap-6 p-4"
      >
        {@render children()}
      </div>
    {/key}
  </section>
</div>
