<script lang="ts">
  import { ChevronDown } from '$lib/icons';
  import { Collapsible, JsonView } from '$lib/kit';
  import type { DeviceHandle, PropertyInfo } from '$lib/model';
  import { formatPropDisplay, isStructuredValue, PropInput } from '$lib/prop';

  interface Props {
    device: DeviceHandle;
    exclude?: string[];
  }

  const { device, exclude = [] }: Props = $props();
  const properties = $derived.by(() => {
    const entries = (Object.entries(device.interface?.properties ?? {}) as Array<[string, PropertyInfo]>).filter(
      ([name]) => !exclude.includes(name)
    );
    const editable = entries.filter(
      ([name, info]) => info.access === 'rw' && !isStructuredValue(device.getProp(name)?.value)
    );
    const readonly = entries.filter(
      ([name, info]) => info.access === 'ro' || (info.access === 'rw' && isStructuredValue(device.getProp(name)?.value))
    );
    return { editable, readonly };
  });

  function isStructuredProperty(name: string): boolean {
    return isStructuredValue(device.getProp(name)?.value);
  }
</script>

{#if properties.editable.length > 0 || properties.readonly.length > 0}
  <div class="space-y-5">
    {#if properties.editable.length > 0}
      <div class="grid gap-2">
        {#each properties.editable as [name, info] (name)}
          <div class="flex items-center justify-between gap-6">
            <span class="shrink-0 text-fg" title={info.desc ?? ''}>{info.label}</span>
            <div class="w-full max-w-64 min-w-0">
              <PropInput model={device.getProp(name)?.model} size="sm" />
            </div>
          </div>
        {/each}
      </div>
    {/if}

    {#if properties.readonly.length > 0}
      <div class="grid gap-1.5">
        {#each properties.readonly as [name, info] (name)}
          {#if isStructuredProperty(name)}
            <Collapsible.Root>
              <Collapsible.Trigger class="flex h-5 w-full items-center justify-between">
                <span class="text-fg-muted">{info.label}</span>
                <ChevronDown
                  class="h-3.5 w-3.5 -rotate-90 text-fg-muted/60 transition-transform duration-200 [[data-state=open]>&]:rotate-0"
                />
              </Collapsible.Trigger>
              <Collapsible.Content class="pt-1">
                <div class="rounded border border-border bg-card p-2">
                  <JsonView data={device.getProp(name)?.value} />
                </div>
              </Collapsible.Content>
            </Collapsible.Root>
          {:else}
            <div class="flex min-h-5 items-baseline justify-between gap-6">
              <span class="shrink-0 text-fg-muted" title={info.desc ?? ''}>{info.label}</span>
              <span class="font-mono text-fg-muted">
                {formatPropDisplay(device.getProp(name)?.value, info.units || undefined)}
              </span>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
  </div>
{/if}
