<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import { Button, DropdownMenu } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { reportFailure } from '@voxel/kit/failures';
  import { displayName } from '@voxel/kit/format';
  import { Check, TriangleAlert } from '@voxel/kit/icons';

  import type { InstrumentSelection } from './selection.svelte';

  let { selection, disabled = false }: { selection: InstrumentSelection; disabled?: boolean } = $props();

  const station = getVoxelStation();

  let names = $state<HTMLElement | null>(null);
  let open = $state(false);

  const openName = $derived(station.session?.instrument.name ?? null);
  const selected = $derived(selection.selected);
  const changing = $derived(station.status === 'opening' || station.status === 'closing');
  const instruments = $derived(
    Object.entries(station.instruments).sort(([left], [right]) => left.localeCompare(right))
  );
</script>

<DropdownMenu.Root
  bind:open
  onOpenChange={(next) => (next ? reportFailure(station.loadInstruments()) : selection.cancel())}
>
  <DropdownMenu.Trigger
    {disabled}
    class="group -ml-2 flex min-w-0 cursor-pointer items-center self-stretch focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-40"
    aria-label={`Station and instrument menu: ${station.name}, ${selected ? displayName(selected) : 'no instrument'}${selected && selected === openName ? ', open' : ''}`}
  >
    <span
      bind:this={names}
      class="flex h-ui-sm min-w-0 items-center gap-1.5 rounded-md px-2 transition-colors group-hover:bg-element-hover group-data-[state=open]:bg-element-hover"
    >
      <span class="min-w-0 truncate text-fg-muted">{station.name}</span>
      <span class="shrink-0 text-fg-faint" aria-hidden="true">/</span>
      <span class="min-w-0 truncate font-medium text-fg">{selected ? displayName(selected) : 'Select instrument…'}</span
      >
    </span>
  </DropdownMenu.Trigger>

  <DropdownMenu.Content customAnchor={names} side="bottom" align="start" sideOffset={6} class="w-72">
    {#each instruments as [name, folder] (name)}
      {@const open = name === openName}
      {@const problems = folder.problems.length}
      <DropdownMenu.Item
        class={cn(name === selected && 'bg-element-selected data-highlighted:bg-element-selected')}
        aria-label={`${displayName(name)}${open ? ', open' : ''}${problems ? `, ${problems} ${problems === 1 ? 'problem' : 'problems'}` : ''}`}
        onclick={() => selection.select(name)}
      >
        <span class="min-w-0 flex-1 truncate">{displayName(name)}</span>
        {#if open}<span class="shrink-0 text-sm text-fg-muted">Open</span>{/if}
        {#if problems}
          <span
            class={cn(
              'flex shrink-0 items-center gap-1 text-sm',
              selection.blocked(name) ? 'text-danger-fg' : 'text-warning-fg'
            )}
          >
            <TriangleAlert class="size-3.5" aria-hidden="true" />
            {problems}
            {problems === 1 ? 'problem' : 'problems'}
          </span>
        {/if}
        {#if name === selected}<Check class="size-4 shrink-0" aria-hidden="true" />{/if}
      </DropdownMenu.Item>
    {:else}
      <DropdownMenu.Item disabled>No instruments</DropdownMenu.Item>
    {/each}
    {#if !changing && openName}
      <DropdownMenu.Separator />
      {#if selection.asking}
        <div class="grid gap-2 rounded-sm bg-tint p-2">
          <p class="text-sm">Close {displayName(openName)}?</p>
          <div class="flex justify-end gap-1">
            <Button size="sm" variant="ghost" disabled={selection.closing} onclick={() => selection.cancel()}
              >Cancel</Button
            >
            <Button
              size="sm"
              variant="danger"
              disabled={selection.closing}
              onclick={async () => {
                await selection.close();
                open = false;
              }}>Close</Button
            >
          </div>
        </div>
      {:else}
        <DropdownMenu.Item
          variant="destructive"
          closeOnSelect={false}
          disabled={selection.running}
          onclick={() => selection.askToClose()}
        >
          <span class="min-w-0 flex-1 truncate">Close {displayName(openName)}</span>
          {#if selection.running}<span class="shrink-0 text-sm">Stop the run first</span>{/if}
        </DropdownMenu.Item>
      {/if}
    {/if}
  </DropdownMenu.Content>
</DropdownMenu.Root>
