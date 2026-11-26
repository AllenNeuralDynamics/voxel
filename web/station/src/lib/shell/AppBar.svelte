<script lang="ts">
  import type { Snippet } from 'svelte';

  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { getInstrumentSelection, getVoxelStation } from '$lib/context.svelte';
  import { LEVEL_ICONS } from '$lib/core/levels';
  import type { Action, AppBar, Crumb, CrumbItem } from '$lib/shell/app-bar.svelte';
  import { Breadcrumb, Button, DropdownMenu, RadioBar } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { Check, Ellipsis } from '@voxel/kit/icons';

  /** Fold steps: status icon, history, buttons and custom actions, choices, middle crumbs, primary action. */
  let {
    bar,
    start,
    history,
    end
  }: { bar: AppBar; start: Snippet; history?: { bar: Snippet; menu: Snippet }; end?: Snippet } = $props();

  const STEPS = [0, 1, 2, 3, 4, 5, 6];

  const crumbs = $derived(bar.content.crumbs);
  const status = $derived(bar.content.status ?? null);
  const actions = $derived(bar.content.actions ?? []);

  const station = getVoxelStation();
  const selection = getInstrumentSelection();
  const closed = $derived(
    selection.selected && selection.selected !== station.session?.instrument.name ? selection.selected : null
  );

  // Measured on hidden copies so a fold never changes what is measured and the bar cannot oscillate.
  let room = $state(0);
  let widths = $state<number[]>([]);
  const step = $derived(STEPS.find((at) => (widths[at] ?? Infinity) <= room) ?? STEPS.length - 1);

  function folds(action: Action, at: number): boolean {
    if ('bar' in action && action.menu === undefined) return false;
    if (action.primary) return at >= 6;
    return at >= ('options' in action ? 4 : 3);
  }
</script>

{#snippet siblingRow(sibling: CrumbItem)}
  {@const open = sibling.href === page.url.pathname}
  <DropdownMenu.Item
    class={cn(open && 'bg-element-selected data-highlighted:bg-element-selected')}
    onclick={() => goto(sibling.href)}
  >
    <span class="min-w-0 flex-1 truncate">{sibling.label}</span>
    {@render sibling.trailing?.()}
    {#if open}<Check class="size-4 shrink-0" aria-hidden="true" />{/if}
  </DropdownMenu.Item>
{/snippet}

{#snippet crumb(item: Crumb, index: number)}
  <Breadcrumb.Separator>/</Breadcrumb.Separator>
  <Breadcrumb.Item class={cn(index === crumbs.length - 1 && 'min-w-0')}>
    {#if 'items' in item}
      <DropdownMenu.Root>
        <DropdownMenu.Trigger
          class="flex h-ui-sm min-w-0 items-center rounded-md px-2 text-fg hover:bg-element-hover data-[state=open]:bg-element-hover"
        >
          <span class="truncate">{item.label}</span>
        </DropdownMenu.Trigger>
        <DropdownMenu.Content align="start" sideOffset={6} class="min-w-56">
          {#each item.items as sibling (sibling.href)}
            {@render siblingRow(sibling)}
          {/each}
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    {:else if 'href' in item}
      <Breadcrumb.Link href={item.href} class="truncate px-1 text-fg-muted">{item.label}</Breadcrumb.Link>
    {:else}
      <Breadcrumb.Page class="truncate px-1 text-fg">{item.label}</Breadcrumb.Page>
    {/if}
  </Breadcrumb.Item>
{/snippet}

{#snippet hiddenCrumbs(hidden: Crumb[])}
  <Breadcrumb.Separator>/</Breadcrumb.Separator>
  <Breadcrumb.Item>
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        class="grid size-ui-sm place-items-center rounded-md text-fg-muted hover:bg-element-hover hover:text-fg data-[state=open]:bg-element-hover"
        aria-label="More levels"
      >
        <Ellipsis class="size-4" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Content align="start" sideOffset={6} class="min-w-48">
        {#each hidden as level (level.label)}
          {#if 'items' in level}
            <DropdownMenu.Sub>
              <DropdownMenu.SubTrigger>{level.label}</DropdownMenu.SubTrigger>
              <DropdownMenu.SubContent class="min-w-48">
                {#each level.items as sibling (sibling.href)}
                  {@render siblingRow(sibling)}
                {/each}
              </DropdownMenu.SubContent>
            </DropdownMenu.Sub>
          {:else}
            <DropdownMenu.Item disabled={!('href' in level)} onclick={() => 'href' in level && goto(level.href)}
              >{level.label}</DropdownMenu.Item
            >
          {/if}
        {/each}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  </Breadcrumb.Item>
{/snippet}

{#snippet inBar(action: Action)}
  {#if 'bar' in action}
    {@render action.bar()}
  {:else if 'options' in action}
    <RadioBar
      aria-label={action.label}
      options={action.options}
      value={action.value}
      onChange={action.onChange}
      display={action.formatLabel}
      disabled={action.disabled}
    />
  {:else}
    <Button
      variant={action.danger ? 'danger' : action.primary ? 'default' : 'secondary'}
      size="md"
      class="text-base"
      disabled={action.disabled}
      onclick={action.onclick}
    >
      {#if action.icon}<action.icon class="size-4" aria-hidden="true" />{/if}
      {action.label}
    </Button>
  {/if}
{/snippet}

{#snippet inMenu(action: Action)}
  {#if 'bar' in action}
    {@render action.menu?.()}
  {:else if 'options' in action}
    <DropdownMenu.Group>
      <DropdownMenu.GroupHeading class="text-fg-muted">{action.label}</DropdownMenu.GroupHeading>
      <DropdownMenu.RadioGroup value={action.value} onValueChange={action.onChange}>
        {#each action.options as option (option)}
          <DropdownMenu.RadioItem value={option} disabled={action.disabled} closeOnSelect={false}>
            {action.formatLabel?.(option) ?? option}
          </DropdownMenu.RadioItem>
        {/each}
      </DropdownMenu.RadioGroup>
    </DropdownMenu.Group>
  {:else}
    <DropdownMenu.Item
      variant={action.danger ? 'destructive' : 'default'}
      disabled={action.disabled}
      onclick={action.onclick}
    >
      {#if action.icon}<action.icon class="size-4" aria-hidden="true" />{/if}
      {action.label}
    </DropdownMenu.Item>
  {/if}
{/snippet}

<!-- `live` is the visible copy; the others are only measured. -->
{#snippet row(at: number, live: boolean)}
  {@const shown = actions.filter((action) => !folds(action, at))}
  {@const folded = actions.filter((action) => folds(action, at))}
  <Breadcrumb.Root class={cn('flex min-w-0', !live && 'shrink-0')}>
    <Breadcrumb.List class="gap-0 text-base">
      {#if at >= 5 && crumbs.length > 1}
        {@render hiddenCrumbs(crumbs.slice(0, -1))}
        {@render crumb(crumbs[crumbs.length - 1], crumbs.length - 1)}
      {:else}
        {#each crumbs as item, index (index)}
          {@render crumb(item, index)}
        {/each}
      {/if}
    </Breadcrumb.List>
  </Breadcrumb.Root>
  <span class="min-w-3 flex-1"></span>
  {#if closed}
    {@const found = station.instruments[closed]?.problems ?? []}
    {@const errors = found.filter((problem) => problem.level !== 'warning').length}
    {@const fatal = found.filter((problem) => problem.level === 'fatal').length}
    {@const warnings = found.length - errors}
    {@const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`}
    <!-- The files' problems, by level: only before opening, since an open instrument shows its live issues below. -->
    {#each [['fatal', fatal, 'fatal problem'], ['error', errors - fatal, 'error']] as const as [level, count, word] (level)}
      {#if count > 0}
        {@const Icon = LEVEL_ICONS[level]}
        <a
          class="relative flex h-ui-xs shrink-0 items-center gap-1 rounded-sm bg-danger-tint px-1.5 text-sm text-danger-fg tabular-nums hover:underline"
          href={selection.problemsHref(closed)}
          title="{plural(count, word)} in the files"
          ><Icon class="size-3" aria-hidden="true" />{count}<span class="sr-only">
            {plural(count, word).slice(String(count).length)}</span
          ></a
        >
      {/if}
    {/each}
    {#if warnings > 0}
      <a
        class="relative flex h-ui-xs shrink-0 items-center gap-1 rounded-sm bg-warning-tint px-1.5 text-sm text-warning-fg tabular-nums hover:underline"
        href={selection.problemsHref(closed)}
        title="{plural(warnings, 'warning')} in the files"
        ><LEVEL_ICONS.warning class="size-3" aria-hidden="true" />{warnings}<span class="sr-only">
          {warnings === 1 ? 'warning' : 'warnings'}</span
        ></a
      >
    {/if}
  {/if}
  {#if status}
    <span
      class="flex shrink-0 items-center gap-1.5 text-fg-muted"
      title={at >= 1 ? status.label : undefined}
      aria-label={at >= 1 ? status.label : undefined}
      role={at >= 1 ? 'img' : undefined}
    >
      <status.icon class="size-4" aria-hidden="true" />
      {#if at < 1}<span class="whitespace-nowrap">{status.label}</span>{/if}
    </span>
  {/if}
  {#each shown as action, index (index)}
    <div class="flex shrink-0 items-center">{@render inBar(action)}</div>
  {/each}
  {#if history && at < 2}{@render history.bar()}{/if}
  {#if folded.length > 0 || (history && at >= 2)}
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>
        {#snippet child({ props })}
          <Button {...props} variant="secondary" size="icon" class="shrink-0" aria-label="More actions">
            <Ellipsis class="size-4" />
          </Button>
        {/snippet}
      </DropdownMenu.Trigger>
      <DropdownMenu.Content align="end" sideOffset={6} class="min-w-52">
        {#each folded as action, index (index)}
          {#if index > 0 && ('options' in action || 'options' in folded[index - 1])}
            <DropdownMenu.Separator />
          {/if}
          {@render inMenu(action)}
        {/each}
        {#if history && at >= 2}
          {#if folded.length > 0}<DropdownMenu.Separator />{/if}
          {@render history.menu()}
        {/if}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  {/if}
  {#if closed}
    {@const found = station.instruments[closed]?.problems ?? []}
    {@const errors = found.filter((problem) => problem.level !== 'warning').length}
    {@const fatal = found.filter((problem) => problem.level === 'fatal').length}
    {@const warnings = found.length - errors}
    {@const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`}
    {#if selection.running}<span class="shrink-0 text-sm whitespace-nowrap text-fg-muted">Stop the run first</span>{/if}
    <!-- The wrapper holds the tooltip, since a disabled button shows none in some browsers. -->
    <span class="inline-flex shrink-0" title={fatal > 0 ? `Cannot open: ${plural(fatal, 'fatal problem')}` : undefined}>
      <Button
        size="sm"
        class="shrink-0"
        disabled={fatal > 0 || station.status === 'opening' || selection.running}
        onclick={() => closed && selection.askToOpen(closed)}
        >{station.status === 'opening' ? 'Opening…' : 'Open'}</Button
      >
    </span>
  {/if}
  <!-- `contents` so an empty `end` adds no gap. -->
  {#if end}<div class="contents">{@render end()}</div>{/if}
{/snippet}

<div class="flex h-full min-w-0 flex-1 items-center">
  {@render start()}
  <div class="relative flex h-full min-w-0 flex-1 items-center gap-2" bind:clientWidth={room}>
    {@render row(step, true)}
    {#each STEPS as at (at)}
      <div
        class="pointer-events-none invisible absolute top-0 left-0 flex h-full w-max items-center gap-2"
        aria-hidden="true"
        inert
        bind:offsetWidth={widths[at]}
      >
        {@render row(at, false)}
      </div>
    {/each}
  </div>
</div>
