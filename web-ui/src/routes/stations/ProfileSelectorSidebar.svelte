<script lang="ts">
  import { Select } from 'bits-ui';

  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { Check, ChevronsUpDown, DotsSpinner } from '$lib/icons';
  import { selectVariants } from '$lib/kit/Select.svelte';
  import type { Instrument } from '$lib/model';
  import { cn, displayName } from '$lib/utils';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  let { instrument, class: className }: Props = $props();

  let pending = $state<string | null>(null);
  let switching = $state(false);
  const selected = $derived(pending ?? instrument.activeProfileId);
  const profiles = $derived(
    Object.entries(instrument.imaging.profiles).map(([id, profile]) => ({
      value: id,
      label: profile.label ?? displayName(id),
      description: profile.desc
    }))
  );
  const items = $derived(profiles.map((profile) => ({ value: profile.value, label: profile.label })));
  const selectedLabel = $derived(profiles.find((profile) => profile.value === selected)?.label ?? '');
  const styles = selectVariants({ variant: 'ghost', size: 'md' });

  async function handleChange(value: string | undefined) {
    if (!value) return;
    pending = value;
    switching = true;
    try {
      if (page.params.profileId) {
        await goto(
          resolve('/stations/[stationId]/instruments/[instrumentId]/profiles/[profileId]/overview', {
            stationId: page.params.stationId ?? '',
            instrumentId: page.params.instrumentId ?? '',
            profileId: value
          })
        );
      } else {
        await instrument.setActiveProfile(value);
      }
    } finally {
      switching = false;
      pending = null;
    }
  }
</script>

<Select.Root type="single" value={selected} onValueChange={handleChange} {items} disabled={switching}>
  <div class={cn('relative min-w-0', className)}>
    <Select.Trigger
      class={cn(
        styles.trigger(),
        'w-full cursor-pointer border-transparent bg-transparent px-2 text-left text-lg hover:border-transparent hover:bg-element-hover disabled:opacity-40 data-[state=open]:bg-element-hover'
      )}
      title={selectedLabel || 'Select profile'}
    >
      <span class="min-w-0 flex-1 truncate text-left">
        {#if selectedLabel}
          {selectedLabel}
        {:else}
          <span class="text-fg-muted">Select profile…</span>
        {/if}
      </span>
      {#if switching}
        <DotsSpinner class="shrink-0 text-fg-muted" width="14" height="14" />
      {:else}
        <ChevronsUpDown class="shrink-0" width="14" height="14" />
      {/if}
    </Select.Trigger>
  </div>

  <Select.Portal>
    <Select.Content side="right" align="start" sideOffset={14} class={cn(styles.content(), 'w-72 min-w-72')}>
      {#if profiles.length === 0}
        <div class="px-3 py-2 text-base text-fg-muted">No profiles available</div>
      {:else}
        <Select.Viewport class="max-h-(--bits-select-content-available-height) overflow-y-auto">
          <Select.Group>
            {#each profiles as profile (profile.value)}
              <Select.Item
                value={profile.value}
                label={profile.label}
                class={cn(
                  styles.item(),
                  'data-highlighted:bg-element-active',
                  profile.description ? 'items-start' : 'items-center'
                )}
              >
                <div class="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span class="truncate text-fg">{profile.label}</span>
                  {#if profile.description}
                    <span class="text-base text-fg-muted">{profile.description}</span>
                  {/if}
                </div>
                <span class="inline-flex h-3 w-3 shrink-0 items-center justify-center text-primary">
                  {#if selected === profile.value}
                    <Check class="h-3 w-3" />
                  {/if}
                </span>
              </Select.Item>
            {/each}
          </Select.Group>
        </Select.Viewport>
      {/if}
    </Select.Content>
  </Select.Portal>
</Select.Root>
