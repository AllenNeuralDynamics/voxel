<script lang="ts">
  import { Select } from 'bits-ui';

  import { Check, ChevronUpDown, DotsSpinner } from '$lib/icons';
  import { selectVariants } from '$lib/kit/Select.svelte';
  import type { Instrument } from '$lib/model';
  import { cn, sanitizeString } from '$lib/utils';

  interface Props {
    instrument: Instrument;
    size?: 'xs' | 'sm' | 'md' | 'lg';
    class?: string;
  }

  let { instrument, size = 'md', class: className }: Props = $props();

  // Interaction state, owned here (the backend models neither). `pending` optimistically overrides the
  // shown profile during an async switch; cleared on completion so `selected` resumes following the
  // instrument — which also reflects switches made by other clients. `switching` drives the spinner.
  let pending = $state<string | null>(null);
  let switching = $state(false);
  const selected = $derived(pending ?? instrument.activeProfileId);

  /** Whether any planned task targets this profile (drives the dot indicator). */
  function profileHasTasks(id: string): boolean {
    return Object.values(instrument.state.tasks).some((t) => t.profile_ids.includes(id));
  }

  const profileList = $derived(
    Object.entries(instrument.imaging.profiles).map(([id, cfg]) => ({
      value: id,
      label: cfg.label ?? sanitizeString(id),
      description: cfg.desc
    }))
  );

  const items = $derived(profileList.map((p) => ({ value: p.value, label: p.label })));
  const selectedLabel = $derived(profileList.find((p) => p.value === selected)?.label ?? '');
  const loading = $derived(switching);
  const styles = $derived(selectVariants({ variant: 'filled', size }));

  const iconSize = $derived({ xs: 10, sm: 12, md: 14, lg: 16 }[size]);
  const selectedHasTasks = $derived(profileHasTasks(selected));

  async function handleChange(value: string | undefined) {
    if (!value) return;
    pending = value;
    switching = true;
    try {
      await instrument.setActiveProfile(value);
    } finally {
      switching = false;
      pending = null;
    }
  }
</script>

<Select.Root type="single" value={selected} onValueChange={handleChange} {items} disabled={loading}>
  <div class={cn('relative', className)}>
    <Select.Trigger class={cn(styles.trigger(), 'w-full rounded-md px-3 pr-8')}>
      <span class="flex items-center gap-1.5 truncate">
        <span class="inline-block size-1.5 shrink-0 rounded-full {selectedHasTasks ? 'bg-info' : 'bg-fg-faint/50'}"
        ></span>
        {#if selectedLabel}
          {selectedLabel}
        {:else}
          <span class="text-fg-muted">Select profile...</span>
        {/if}
      </span>
    </Select.Trigger>
    <div class="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2">
      {#if loading}
        <DotsSpinner class="text-fg-muted" width={iconSize} height={iconSize} />
      {:else}
        <ChevronUpDown class="opacity-50" width={iconSize} height={iconSize} />
      {/if}
    </div>
  </div>

  <Select.Portal>
    <Select.Content align="start" sideOffset={4} class={cn(styles.content(), 'bg-surface')}>
      {#if profileList.length === 0}
        <div class="px-3 py-2 text-base text-fg-muted">No profiles available</div>
      {:else}
        <Select.Viewport class="max-h-(--bits-select-content-available-height) overflow-y-auto">
          <Select.Group>
            {#each profileList as profile (profile.value)}
              {@const hasTasks = profileHasTasks(profile.value)}
              <Select.Item
                value={profile.value}
                label={profile.label}
                class={cn(
                  styles.item(),
                  'data-highlighted:bg-floating',
                  profile.description ? 'items-start' : 'items-center'
                )}
              >
                <span
                  class="mt-1.5 inline-block size-1.5 shrink-0 self-start rounded-full {hasTasks
                    ? 'bg-info'
                    : 'bg-fg-faint/50'}"
                ></span>
                <div class="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span class="text-fg">{profile.label}</span>
                  {#if profile.description}
                    <span class="text-xs text-fg-muted">{profile.description}</span>
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
