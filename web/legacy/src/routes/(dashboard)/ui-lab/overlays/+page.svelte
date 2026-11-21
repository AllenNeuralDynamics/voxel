<script lang="ts">
  import type { Snippet } from 'svelte';

  import { Button, ContextMenu, Dialog, DropdownMenu, HoverCard, Popover, Tooltip } from '@voxel/kit';
  import { Check, ChevronDown, ChevronRight, Crosshair, Plus, Square, Undo } from '@voxel/kit/icons';
  import { themes } from '@voxel/kit/style';

  import { lab } from '../lab';
  import LabHeader from '../LabHeader.svelte';
  import NotUsed from '../NotUsed.svelte';

  // The live overlays use the kit defaults. The pictures copy those classes, so keep them in step with `web/kit/src/shadcn`.
  const MENU = 'min-w-32 frame-floating p-1 text-fg';
  const ITEM =
    "flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-base select-none data-highlighted:bg-element-hover data-highlighted:text-fg [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 [&_svg:not([class*='text-'])]:text-fg-muted";
  const SEPARATOR = '-mx-1 my-1 h-px bg-line-faint';
  const TIP = 'relative inline-flex items-center gap-1.5 frame-floating px-2 py-1 text-base text-fg';
  const CARD = 'flex w-60 flex-col gap-2 frame-floating p-3';
  const PANEL = 'grid w-48 grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 frame-floating p-3 text-sm';

  const ZOOMS = ['Fit to window', 'Zoom to 100%'];
  const CHANNEL = [
    ['Laser', '488 nm'],
    ['Camera', 'Camera 1'],
    ['Filter', 'BP525']
  ];
  const LEVELS = [
    ['Black', '0.1 %'],
    ['White', '99.9 %']
  ];

  let zoom = $state('Fit to window');
  let grid = $state(true);
  let scale = $state(false);
  let closeOpen = $state(false);
  const prefs = $derived(themes.prefs.get());
</script>

{#snippet stage(name: string, body: Snippet, unused = false)}
  <figure class="flex flex-col gap-2">
    <div class="relative h-60 overflow-hidden rounded-lg bg-canvas p-3 ring-1 ring-line-faint">{@render body()}</div>
    <figcaption class="flex items-center gap-2 px-1">
      <code class={lab.code}>{name}</code>
      {#if unused}<NotUsed />{/if}
    </figcaption>
  </figure>
{/snippet}

{#snippet tick(on: boolean)}
  <span class="flex size-3.5 shrink-0 items-center"
    >{#if on}<Check class="size-3.5" />{/if}</span
  >
{/snippet}

{#snippet levels()}
  {#each LEVELS as [term, value] (term)}
    <span class="text-fg-muted">{term}</span>
    <span class="text-fg tabular-nums">{value}</span>
  {/each}
{/snippet}

{#snippet channelCard()}
  <span class="text-base font-medium text-fg">GFP</span>
  <dl class="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
    {#each CHANNEL as [term, value] (term)}
      <dt class="text-fg-muted">{term}</dt>
      <dd class="text-fg">{value}</dd>
    {/each}
  </dl>
{/snippet}

<LabHeader title="Overlays" />

<div class={lab.body}>
  <div class="grid grid-cols-3 gap-x-6 gap-y-10">
    {#snippet dropdown()}
      <div class="flex flex-col items-start gap-1">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger>
            {#snippet child({ props })}
              <Button {...props} variant="secondary">View <ChevronDown class="size-3" /></Button>
            {/snippet}
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content align="start" sideOffset={4}>
              {#each ZOOMS as option (option)}
                <DropdownMenu.Item onSelect={() => (zoom = option)}>
                  {@render tick(option === zoom)}{option}
                </DropdownMenu.Item>
              {/each}
              <DropdownMenu.Separator />
              <DropdownMenu.Item closeOnSelect={false} onSelect={() => (grid = !grid)}>
                {@render tick(grid)}Show grid
              </DropdownMenu.Item>
              <DropdownMenu.Item closeOnSelect={false} onSelect={() => (scale = !scale)}>
                {@render tick(scale)}Show scale
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
        <div class={MENU} aria-hidden="true">
          {#each ZOOMS as option (option)}
            <div class={ITEM} data-highlighted={option === 'Zoom to 100%' ? '' : undefined}>
              {@render tick(option === zoom)}{option}
            </div>
          {/each}
          <div class={SEPARATOR}></div>
          <div class={ITEM}>{@render tick(grid)}Show grid</div>
          <div class={ITEM}>{@render tick(scale)}Show scale</div>
        </div>
      </div>
    {/snippet}
    {@render stage('DropdownMenu', dropdown)}

    {#snippet context()}
      <ContextMenu.Root>
        <ContextMenu.Trigger class="absolute inset-3 frame-placeholder p-2.5 text-sm text-fg-muted">
          Right-click here
        </ContextMenu.Trigger>
        <ContextMenu.Portal>
          <ContextMenu.Content>
            <ContextMenu.Sub>
              <ContextMenu.SubTrigger><Plus />Add task</ContextMenu.SubTrigger>
              <ContextMenu.SubContent>
                <ContextMenu.Item>Current stage position</ContextMenu.Item>
                <ContextMenu.Item>Clicked position</ContextMenu.Item>
              </ContextMenu.SubContent>
            </ContextMenu.Sub>
            <ContextMenu.Item><Crosshair />Move here</ContextMenu.Item>
            <ContextMenu.Separator />
            <ContextMenu.Item variant="destructive"><Square />Halt</ContextMenu.Item>
          </ContextMenu.Content>
        </ContextMenu.Portal>
      </ContextMenu.Root>
      <div class="pointer-events-none absolute top-14 left-12 {MENU}" aria-hidden="true">
        <div class={ITEM} data-highlighted=""><Plus />Add task<ChevronRight class="ml-auto" /></div>
        <div class={ITEM}><Crosshair />Move here</div>
        <div class={SEPARATOR}></div>
        <div class={ITEM}><Square />Halt</div>
      </div>
    {/snippet}
    {@render stage('ContextMenu', context)}

    {#snippet tip()}
      <div class="flex items-center gap-2">
        <Tooltip.Root>
          <Tooltip.Trigger>
            {#snippet child({ props })}
              <Button {...props} variant="ghost" size="icon" aria-label="Undo"><Undo class="size-4" /></Button>
            {/snippet}
          </Tooltip.Trigger>
          <Tooltip.Content side="right" sideOffset={8}>
            Undo Laser 405 power <kbd class={lab.key}>⌘Z</kbd>
          </Tooltip.Content>
        </Tooltip.Root>
        <span class={TIP} aria-hidden="true">
          <span class="absolute top-1/2 -left-1 size-2.5 -translate-y-1/2 rotate-45 rounded-[2px] bg-floating"></span>
          <span class="relative">Undo Laser 405 power</span>
          <kbd class="relative {lab.key}">⌘Z</kbd>
        </span>
      </div>
    {/snippet}
    {@render stage('Tooltip', tip)}

    {#snippet card()}
      <div class="flex flex-col items-start gap-1.5">
        <HoverCard.Root openDelay={200}>
          <HoverCard.Trigger
            class="inline-flex items-center gap-1.5 rounded-sm bg-element-bg px-1.5 text-sm/5  text-fg hover:bg-element-hover"
          >
            <span class="size-2 rounded-full bg-success-fg"></span>GFP
          </HoverCard.Trigger>
          <HoverCard.Content class={CARD} align="start" sideOffset={6}>{@render channelCard()}</HoverCard.Content>
        </HoverCard.Root>
        <div class={CARD} aria-hidden="true">{@render channelCard()}</div>
      </div>
    {/snippet}
    {@render stage('HoverCard', card, true)}

    {#snippet popover()}
      <div class="flex flex-col items-start gap-1.5">
        <Popover.Root>
          <Popover.Trigger>
            {#snippet child({ props })}
              <Button {...props} variant="secondary" size="sm">Levels<ChevronDown class="size-3.5" /></Button>
            {/snippet}
          </Popover.Trigger>
          <Popover.Content class={PANEL} align="start">{@render levels()}</Popover.Content>
        </Popover.Root>
        <div class={PANEL} aria-hidden="true">{@render levels()}</div>
      </div>
    {/snippet}
    {@render stage('Popover', popover)}

    {#snippet dialog()}
      <Button variant="secondary" onclick={() => (closeOpen = true)}>Close the instrument</Button>
      <div
        class="absolute inset-x-0 top-[calc(var(--ui-sm)+var(--spacing)*6)] bottom-0 flex items-center justify-center bg-backdrop"
        inert
      >
        <div class="flex w-60 flex-col gap-2 frame-dialog p-3">
          <span class="text-base font-medium text-fg">Close the instrument?</span>
          <span class="text-sm text-fg-muted">The hardware of ExaSPIM disconnects.</span>
          <span class="mt-1 flex justify-end gap-1.5">
            <Button variant="secondary" size="xs">Cancel</Button>
            <Button variant="danger" size="xs">Close</Button>
          </span>
        </div>
      </div>
    {/snippet}
    {@render stage('Dialog', dialog)}

    {#snippet sheet()}
      <div class="absolute inset-y-0 right-0 flex w-40 flex-col gap-3 frame-dialog rounded-none p-3" aria-hidden="true">
        <span class="text-base font-semibold text-fg">Appearance</span>
        <dl class="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1.5 text-sm">
          <dt class="text-fg-muted">Density</dt>
          <dd class="text-fg tabular-nums">{prefs.density} px</dd>
          <dt class="text-fg-muted">Mode</dt>
          <dd class="text-fg capitalize">{prefs.mode}</dd>
        </dl>
      </div>
    {/snippet}
    {@render stage('Sheet', sheet)}
  </div>
</div>

<Dialog.Root bind:open={closeOpen}>
  <Dialog.Content size="sm" showCloseButton={false}>
    <Dialog.Header>
      <Dialog.Title>Close the instrument?</Dialog.Title>
    </Dialog.Header>
    <p class="text-lg text-fg-muted">The hardware of <span class="font-medium text-fg">ExaSPIM</span> disconnects.</p>
    <Dialog.Footer>
      <Button variant="secondary" size="md" onclick={() => (closeOpen = false)}>Cancel</Button>
      <Button variant="danger" size="md" onclick={() => (closeOpen = false)}>Close</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
