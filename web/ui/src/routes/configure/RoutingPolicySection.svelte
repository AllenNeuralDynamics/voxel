<script lang="ts">
  import { watch } from 'runed';

  import { ChevronDown, ChevronRight } from '$lib/icons';
  import { Collapsible } from '$lib/kit';
  import type { Instrument } from '$lib/model';
  import { cn, pref, sanitizeString } from '$lib/utils';

  import RoutingPolicyEditor from './RoutingPolicyEditor.svelte';

  let { instrument }: { instrument: Instrument } = $props();

  const expanded = pref('configure:routing-expanded', true);
  const dimensions = $derived(instrument.routingDimensions);
  let activeId = $state('');

  watch(
    () => dimensions.map(({ id }) => id).join(','),
    () => {
      if (!dimensions.some(({ id }) => id === activeId)) activeId = dimensions[0]?.id ?? '';
    }
  );

  const active = $derived(dimensions.find(({ id }) => id === activeId) ?? dimensions[0]);
</script>

{#if dimensions.length > 0}
  <Collapsible.Root bind:open={expanded.get, expanded.set}>
    <section>
      <Collapsible.Trigger
        class="group flex w-full items-start gap-2 text-left text-fg transition-colors hover:text-fg"
      >
        <div class="min-w-0 flex-1">
          <div class="flex items-baseline gap-2">
            <h3 class="font-medium tracking-wide text-fg-muted uppercase">Optical routing</h3>
            <span class="font-mono text-sm text-fg-faint tabular-nums">{dimensions.length}</span>
          </div>
        </div>
        <span class="mt-0.5 ml-auto shrink-0 text-fg-muted">
          {#if expanded.get()}<ChevronDown width="14" height="14" />{:else}<ChevronRight width="14" height="14" />{/if}
        </span>
      </Collapsible.Trigger>

      <Collapsible.Content class="pt-3">
        {#if dimensions.length > 1}
          <div class="mb-3 flex max-w-full gap-1 overflow-x-auto border-b border-border">
            {#each dimensions as dimension (dimension.id)}
              <button
                type="button"
                class={cn(
                  'shrink-0 border-b-2 px-3 py-1.5 text-base transition-colors',
                  active?.id === dimension.id ? 'border-fg text-fg' : 'border-transparent text-fg-muted hover:text-fg'
                )}
                onclick={() => (activeId = dimension.id)}
              >
                {sanitizeString(dimension.id)}
              </button>
            {/each}
          </div>
        {/if}

        {#if active}
          <RoutingPolicyEditor {instrument} dimension={active} />
        {/if}
      </Collapsible.Content>
    </section>
  </Collapsible.Root>
{/if}
