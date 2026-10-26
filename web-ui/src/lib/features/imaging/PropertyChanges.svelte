<script lang="ts">
  import { reportFailure } from '$lib/core/failures';
  import type { Instrument } from '$lib/core/model';
  import { cn, displayName } from '$lib/core/utils';
  import { Button } from '$lib/kit';
  import { RotateCcw } from '$lib/kit/icons';

  import { type PropertyChange, propertyChanges } from './changes';

  interface Props {
    instrument: Instrument;
    class?: string;
  }

  let { instrument, class: className }: Props = $props();

  const changes = $derived(propertyChanges(instrument));
  const RUNNING = 'Wait until the run ends';

  /** Why a value cannot be put back now, or null when it can. */
  function blockReason(change: PropertyChange): string | null {
    if (instrument.busy) return RUNNING;
    if (!change.device.connected) return `${displayName(change.device.id)} is disconnected`;
    if (change.device.error) return `${displayName(change.device.id)} has an error`;
    return null;
  }
</script>

<div class={cn('flex h-full min-h-0 flex-col overflow-hidden', className)}>
  <div class="bottom-panel-bar">
    <!-- Restoring is safe to repeat, so it stays on when nothing differs. It waits while a capture runs. -->
    <Button
      variant="quiet"
      size="xs"
      class="ml-auto"
      disabled={instrument.busy}
      title={instrument.busy ? RUNNING : 'Put every device back to the saved profile'}
      onclick={() => reportFailure(instrument.applySettings())}>Restore all</Button
    >
  </div>
  <div class="bottom-panel-box">
    {#if changes.length === 0}
      <p class="flex h-full items-center justify-center text-fg-muted">Nothing differs from the saved profile.</p>
    {:else}
      <table class="w-full" aria-label="Changed properties">
        <thead>
          <tr class="text-left text-fg-muted">
            <th class="px-2 py-1.5 font-normal">Device</th>
            <th class="px-2 py-1.5 font-normal">Property</th>
            <th class="px-2 py-1.5 font-normal">Saved</th>
            <th class="px-2 py-1.5 font-normal">Live</th>
            <th class="w-0 py-1.5 pr-2 font-normal"><span class="sr-only">Restore</span></th>
          </tr>
        </thead>
        <tbody>
          {#each changes as change (change.key)}
            {@const blocked = blockReason(change)}
            <tr class="border-t border-line-faint">
              <td class="px-2 py-1 whitespace-nowrap text-fg-muted">{displayName(change.device.id)}</td>
              <td class="w-full px-2 py-1 text-fg">{change.label}</td>
              <td class="px-2 py-1 font-mono whitespace-nowrap text-fg-muted tabular-nums">{change.saved}</td>
              <td class="px-2 py-1 font-mono whitespace-nowrap text-fg tabular-nums" title={change.detail}
                >{change.live}</td
              >
              <td class="py-1 pr-2">
                <button
                  type="button"
                  class="flex size-6 items-center justify-center rounded-sm text-fg transition-colors focus-visible:outline-2 focus-visible:outline-focus enabled:hover:bg-element-hover disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={blocked !== null}
                  title={blocked ?? 'Put back the saved value'}
                  aria-label={`Restore ${displayName(change.device.id)} ${change.label}`}
                  onclick={() => reportFailure(change.restore())}
                >
                  <RotateCcw class="size-3.5" />
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
</div>
