<script lang="ts">
  import { resolve } from '$app/paths';
  import { cn, sanitizeString } from '$lib/utils';

  import type { Device } from './_device.svelte';

  interface Props {
    device: Device;
  }

  let { device }: Props = $props();
</script>

<a
  href={resolve(`/devices/${device.id}` as '/')}
  class={cn(
    'block rounded-lg border bg-card p-3 text-sm text-fg shadow-sm transition-colors',
    'hover:border-fg-faint hover:bg-element-hover'
  )}
>
  <div class="flex items-center justify-between gap-2">
    <div class="flex min-w-0 items-center gap-2">
      <span
        class="h-1.5 w-1.5 shrink-0 rounded-full {device.connected ? 'bg-success' : 'bg-fg-muted/30'}"
        title={device.connected ? 'Connected' : 'Disconnected'}
      ></span>
      <span class="truncate font-medium text-fg">{sanitizeString(device.id)}</span>
    </div>
    {#if device.interface?.type}
      <span class="shrink-0 rounded bg-element-bg px-1.5 py-0.5 text-xs text-fg-muted">
        {device.interface.type}
      </span>
    {/if}
  </div>
  {#if device.error}
    <p class="mt-2 text-xs text-danger">{device.error}</p>
  {/if}
</a>
