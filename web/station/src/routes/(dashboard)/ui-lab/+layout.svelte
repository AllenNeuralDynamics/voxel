<script lang="ts">
  import { onNavigate } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { Collapsible } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { ChevronDown } from '@voxel/kit/icons';
  import { pref } from '@voxel/kit/pref';
  import { MarkSettings, ThemePicker } from '@voxel/kit/style';

  import { GROUPS, OVERVIEW, PAGES } from './nav';

  let { children } = $props();

  const CARD = 'rounded-lg bg-shell shadow-(--raised-shadow)';

  const current = $derived(PAGES.find((item) => item.route === page.route.id));
  const marksOpen = pref('ui-lab:marks-open', false);

  /** Scrolls the page list, and only the list, so a hidden row of the open page shows in its middle. */
  function showCurrentRow(nav: HTMLElement): void {
    if (!current) return;
    const row = nav.querySelector(`a[href="${resolve(current.route)}"]`);
    if (!row) return;
    const list = nav.getBoundingClientRect();
    const box = row.getBoundingClientRect();
    if (box.top >= list.top && box.bottom <= list.bottom) return;
    nav.scrollTop += box.top - list.top - (list.height - box.height) / 2;
  }

  onNavigate((navigation) => {
    const inLab = (id: string | null | undefined) => id?.startsWith(OVERVIEW) ?? false;
    if (!inLab(navigation.from?.route.id) || !inLab(navigation.to?.route.id)) return;
    if (!document.startViewTransition || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    return new Promise((done) => {
      document.startViewTransition(async () => {
        done();
        await navigation.complete;
      });
    });
  });
</script>

<svelte:head><title>{current ? `${current.label} · UI Lab` : 'UI Lab'}</title></svelte:head>

<div class="grid items-start gap-4 pt-3 pb-8 lg:grid-cols-[22rem_minmax(0,1fr)]">
  <aside
    class="flex min-h-0 flex-col gap-4 lg:sticky lg:top-[calc(var(--app-bar-height)+var(--spacing)*3)] lg:max-h-[calc(100dvh-var(--app-bar-height)-var(--spacing)*11)]"
  >
    <section class={cn(CARD, 'flex shrink-0 flex-col gap-4 p-4')} aria-labelledby="appearance-heading">
      <h2 id="appearance-heading" class="text-base font-medium text-fg">Appearance</h2>
      <ThemePicker />
      <Collapsible.Root
        bind:open={() => marksOpen.get(), (open) => marksOpen.set(open)}
        class="border-t border-line-faint pt-3"
      >
        <Collapsible.Trigger
          class="group flex h-ui-sm w-full items-center rounded-sm text-base font-medium text-fg focus-visible:outline-2 focus-visible:outline-focus"
        >
          Marks and axes
          <ChevronDown
            class="ml-auto size-3.5 text-fg-muted transition-transform group-data-[state=closed]:-rotate-90"
          />
        </Collapsible.Trigger>
        <Collapsible.Content>
          <div class="pt-3">
            <MarkSettings />
          </div>
        </Collapsible.Content>
      </Collapsible.Root>
    </section>

    <nav {@attach showCurrentRow} aria-label="UI Lab" class={cn(CARD, 'min-h-0 flex-1 overflow-y-auto p-1.5')}>
      {#each GROUPS as group, index (group.label)}
        {#if group.pages.length}
          <h2
            class={cn(
              'px-2.5 pb-1 text-sm text-fg-muted',
              index > 0 ? 'mt-1.5 border-t border-line-faint pt-2.5' : 'pt-1'
            )}
          >
            {group.label}
          </h2>
          <ul class="flex flex-col">
            {#each group.pages as item (item.route)}
              {@const selected = item.route === page.route.id}
              <li>
                <a
                  href={resolve(item.route)}
                  class={cn(
                    'relative flex h-ui-sm items-center rounded-md px-2.5 text-base transition-colors focus-visible:outline-2 focus-visible:outline-focus',
                    selected
                      ? 'font-medium text-fg before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-current'
                      : 'text-fg-muted hover:bg-element-hover hover:text-fg'
                  )}
                  aria-current={selected ? 'page' : undefined}>{item.label}</a
                >
              </li>
            {/each}
          </ul>
        {/if}
      {/each}
    </nav>
  </aside>

  <main class={cn(CARD, 'min-w-0 px-5')}>
    {@render children()}
  </main>
</div>
