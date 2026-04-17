<script lang="ts">
  import type { Session } from '$lib/app';
  import { resolve } from '$app/paths';
  import { sanitizeString, cn } from '$lib/utils';

  interface Props {
    session: Session;
    deviceId: string;
  }

  let { session, deviceId }: Props = $props();

  const device = $derived(session.devices.devices.get(deviceId));
  const type = $derived(device?.interface?.type);
  const connected = $derived(device?.connected ?? false);
  const error = $derived(device?.error);
</script>

{#if device}
  <a
    href={resolve(`/devices/${deviceId}` as '/')}
    class={cn(
      'block rounded-lg border bg-card p-3 text-sm text-fg shadow-sm transition-colors',
      'hover:border-fg-faint hover:bg-element-hover'
    )}
  >
    <div class="flex items-center justify-between gap-2">
      <div class="flex min-w-0 items-center gap-2">
        <span
          class="h-1.5 w-1.5 shrink-0 rounded-full {connected ? 'bg-success' : 'bg-fg-muted/30'}"
          title={connected ? 'Connected' : 'Disconnected'}
        ></span>
        <span class="truncate font-medium text-fg">{sanitizeString(deviceId)}</span>
      </div>
      {#if type}
        <span class="shrink-0 rounded bg-element-bg px-1.5 py-0.5 text-xs text-fg-muted">
          {type}
        </span>
      {/if}
    </div>
    {#if error}
      <p class="mt-2 text-xs text-danger">{error}</p>
    {/if}
  </a>
{/if}
