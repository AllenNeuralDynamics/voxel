<script lang="ts">
  import type { Snippet } from 'svelte';

  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { getInstrumentSelection, getVoxelStation } from '$lib/context.svelte';
  import type { Action, AppBar, Crumb } from '$lib/shell/app-bar.svelte';
  import { Breadcrumb, Button, DropdownMenu, RadioBar } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { displayName } from '@voxel/kit/format';
  import { Check, Ellipsis } from '@voxel/kit/icons';

  /**
   * The page's app bar: `start` (the station menu), then the page's crumbs, its status and its actions. When they do
   * not fit, parts fold in steps: 1 the status shows only its icon, 2 buttons and custom actions go into a menu, 3 so
   * do choices, 4 the crumbs between `start` and the last fold into a menu. A primary action, and a custom action
   * without a menu, never fold. The last crumb truncates when even step 4 does not fit. At the end, while another
   * instrument than the one on show is open, the bar names it; a click shows it. That never folds either.
   */
  let { bar, start }: { bar: AppBar; start: Snippet } = $props();

  const STEPS = [0, 1, 2, 3, 4];

  const crumbs = $derived(bar.content.crumbs);
  const status = $derived(bar.content.status ?? null);
  const actions = $derived(bar.content.actions ?? []);

  const station = getVoxelStation();
  const selection = getInstrumentSelection();
  const elsewhere = $derived.by(() => {
    const open = station.session?.instrument_name;
    return open && open !== selection.selected ? open : null;
  });

  // The width that is left after `start`, and the width the row takes at each step, measured on hidden copies. So a
  // fold never changes what is measured, and the bar does not flip between 2 steps.
  let room = $state(0);
  let widths = $state<number[]>([]);
  const step = $derived(STEPS.find((at) => (widths[at] ?? Infinity) <= room) ?? STEPS.length - 1);

  function folds(action: Action, at: number): boolean {
    if (action.primary) return false;
    if ('options' in action) return at >= 3;
    if ('bar' in action) return action.menu !== undefined && at >= 2;
    return at >= 2;
  }
</script>

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
            <DropdownMenu.Item onclick={() => goto(sibling.href)}>
              <span class="flex-1 truncate">{sibling.label}</span>
              {#if sibling.href === page.url.pathname}<Check class="size-4 shrink-0" aria-hidden="true" />{/if}
            </DropdownMenu.Item>
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
                  <DropdownMenu.Item onclick={() => goto(sibling.href)}>
                    <span class="flex-1 truncate">{sibling.label}</span>
                    {#if sibling.href === page.url.pathname}<Check class="size-4 shrink-0" aria-hidden="true" />{/if}
                  </DropdownMenu.Item>
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
      formatLabel={action.formatLabel}
      disabled={action.disabled}
    />
  {:else}
    <Button
      variant={action.danger ? 'danger' : action.primary ? 'default' : 'outline'}
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

<!-- The row after `start` at 1 step. `live` is the copy on show; the others are only measured. -->
{#snippet row(at: number, live: boolean)}
  {@const shown = actions.filter((action) => !folds(action, at))}
  {@const folded = actions.filter((action) => folds(action, at))}
  <Breadcrumb.Root class={cn('flex min-w-0', !live && 'shrink-0')}>
    <Breadcrumb.List class="gap-0 text-base">
      {#if at >= 4 && crumbs.length > 1}
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
  {#if folded.length > 0}
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>
        {#snippet child({ props })}
          <Button {...props} variant="ghost" size="icon-sm" class="shrink-0 text-fg-muted" aria-label="More actions">
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
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  {/if}
  {#if elsewhere}
    <button
      type="button"
      class="h-ui-sm shrink-0 rounded-md px-2 whitespace-nowrap text-warning-fg hover:bg-element-hover"
      onclick={() => elsewhere && selection.select(elsewhere)}>{displayName(elsewhere)} is open</button
    >
  {/if}
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
