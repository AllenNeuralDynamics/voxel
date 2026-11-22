<script lang="ts">
  import { getVoxelStation } from '$lib/context.svelte';
  import type { InstrumentFolder } from '$lib/model/station.svelte';
  import { Button, DropdownMenu } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { reportFailure } from '@voxel/kit/failures';
  import { displayName } from '@voxel/kit/format';
  import { Check, TriangleAlert } from '@voxel/kit/icons';

  import type { InstrumentSelection } from './selection.svelte';

  /** The station's name and the selected instrument, with a menu of the station's instruments. */
  let { selection, disabled = false }: { selection: InstrumentSelection; disabled?: boolean } = $props();

  const station = getVoxelStation();

  let names = $state<HTMLElement | null>(null);
  let open = $state(false);

  const openName = $derived(station.session?.instrument_name ?? null);
  const selected = $derived(selection.selected);
  const changing = $derived(station.status === 'opening' || station.status === 'closing');
  const instruments = $derived(
    Object.entries(station.instruments).sort(([left], [right]) => left.localeCompare(right))
  );

  function issue(folder: InstrumentFolder): string | null {
    return folder.problems.length > 0 ? folder.problems.map((problem) => problem.msg).join('\n') : null;
  }
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
      <span class={cn('min-w-0 truncate', openName ? 'text-success-fg' : 'text-fg-muted')}>{station.name}</span>
      <span class="shrink-0 text-fg-faint" aria-hidden="true">/</span>
      <span
        class={cn('min-w-0 truncate font-medium', selected && selected === openName ? 'text-success-fg' : 'text-fg')}
        >{selected ? displayName(selected) : 'Select instrument…'}</span
      >
    </span>
  </DropdownMenu.Trigger>

  <DropdownMenu.Content customAnchor={names} side="bottom" align="start" sideOffset={6} class="w-72">
    {#each instruments as [name, folder] (name)}
      {@const open = name === openName}
      {@const problems = issue(folder)}
      <DropdownMenu.Item
        disabled={!folder.ok}
        class={cn(name === selected && 'bg-element-selected data-highlighted:bg-element-selected')}
        aria-label={`${displayName(name)}${open ? ', open' : ''}${problems ? ', configuration issues' : ''}`}
        onclick={() => selection.select(name)}
      >
        <span class={cn('min-w-0 flex-1 truncate', open && 'text-success-fg')}>{displayName(name)}</span>
        {#if problems}
          <span class="shrink-0" role="img" aria-label="Configuration issues" title={problems}>
            <TriangleAlert class="size-3.5 text-warning-fg" aria-hidden="true" />
          </span>
        {/if}
        {#if name === selected}<Check class="size-4 shrink-0" aria-hidden="true" />{/if}
      </DropdownMenu.Item>
    {:else}
      <DropdownMenu.Item disabled>No instruments</DropdownMenu.Item>
    {/each}
    {#if !changing && (openName || selected)}
      <DropdownMenu.Separator />
      {#if selection.asking}
        <div class="grid gap-2 rounded-sm bg-tint p-2">
          <p class="text-sm">
            {#if selection.pending}
              Close {displayName(openName ?? '')} and open {displayName(selection.pending)}?
            {:else}
              Close {displayName(openName ?? '')}?
            {/if}
          </p>
          <div class="flex justify-end gap-1">
            <Button size="sm" variant="ghost" disabled={selection.closing} onclick={() => selection.cancel()}
              >Cancel</Button
            >
            <Button
              size="sm"
              variant="danger"
              disabled={selection.closing}
              onclick={async () => {
                await selection.confirm();
                open = false;
              }}>{selection.pending ? 'Switch' : 'Close'}</Button
            >
          </div>
        </div>
      {:else}
        {#if selected && selected !== openName}
          <DropdownMenu.Item closeOnSelect={!openName} onclick={() => selection.askToOpen(selected)}>
            Open {displayName(selected)}
          </DropdownMenu.Item>
        {/if}
        {#if openName}
          <DropdownMenu.Item variant="destructive" closeOnSelect={false} onclick={() => selection.askToClose()}>
            Close {displayName(openName)}
          </DropdownMenu.Item>
        {/if}
      {/if}
    {/if}
  </DropdownMenu.Content>
</DropdownMenu.Root>
