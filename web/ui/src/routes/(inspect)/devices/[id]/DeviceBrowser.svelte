<script lang="ts">
  import { ChevronDown } from '$lib/icons';
  import { Collapsible } from '$lib/kit';
  import type { DeviceHandle, PropertyInfo } from '$lib/model';
  import { isStructuredValue } from '$lib/prop';

  import CommandButton from './CommandButton.svelte';
  import PropertyControl from './PropertyControl.svelte';

  interface DeviceExclusions {
    props: string[];
    cmds: string[];
  }

  interface Props {
    device: DeviceHandle;
    exclusions?: DeviceExclusions;
    size?: 'sm' | 'md';
  }

  let { device, exclusions, size = 'sm' }: Props = $props();

  const excludeProps = $derived(new Set(exclusions?.props ?? []));
  const excludeCmds = $derived(new Set(exclusions?.cmds ?? []));

  const filteredProperties = $derived.by(() => {
    const props = device.interface?.properties;
    if (!props) return { rw: [] as Array<[string, PropertyInfo]>, ro: [] as Array<[string, PropertyInfo]> };

    const entries = Object.entries(props).filter(([name]) => !excludeProps.has(name));

    const rw = entries.filter(
      ([name, info]) => info.access === 'rw' && !isStructuredValue(device.getProp(name)?.value)
    );
    const ro = entries.filter(
      ([name, info]) => info.access === 'ro' || (info.access === 'rw' && isStructuredValue(device.getProp(name)?.value))
    );

    return { rw, ro };
  });

  const showRw = $derived(filteredProperties.rw.length > 0);
  const showRo = $derived(filteredProperties.ro.length > 0);

  function isStructuredProp(name: string): boolean {
    return isStructuredValue(device.getProp(name)?.value);
  }

  const commandNames = $derived.by(() => {
    const cmds = device.interface?.commands;
    if (!cmds) return [] as string[];
    return Object.keys(cmds).filter((n) => !excludeCmds.has(n));
  });

  const showCmds = $derived(commandNames.length > 0);
</script>

{#if showRw}
  <div class="grid gap-2">
    {#each filteredProperties.rw as [name, info] (name)}
      <div class="flex items-center justify-between gap-4">
        <span class="shrink-0 text-sm text-fg" title={info.desc ?? ''}>
          {info.label}
        </span>
        <div class="max-w-64 min-w-0">
          <PropertyControl {device} propName={name} {size} />
        </div>
      </div>
    {/each}
  </div>
{/if}

{#if showRo}
  <div class="grid gap-1.5">
    {#each filteredProperties.ro as [name, info] (name)}
      {#if isStructuredProp(name)}
        <Collapsible.Root>
          <Collapsible.Trigger class="flex h-5 w-full items-center justify-between">
            <span class="text-sm text-fg-muted">{info.label}</span>
            <ChevronDown
              class="h-3.5 w-3.5 -rotate-90 text-fg-muted/60 transition-transform duration-200 [[data-state=open]>&]:rotate-0"
            />
          </Collapsible.Trigger>
          <Collapsible.Content class="pt-1">
            <div class="rounded border border-border bg-card p-2">
              <PropertyControl {device} propName={name} {size} />
            </div>
          </Collapsible.Content>
        </Collapsible.Root>
      {:else}
        <div class="flex min-h-5 items-baseline justify-between gap-4">
          <span class="shrink-0 text-sm text-fg-muted" title={info.desc ?? ''}>
            {info.label}
          </span>
          <PropertyControl {device} propName={name} {size} />
        </div>
      {/if}
    {/each}
  </div>
{/if}

{#if showCmds}
  <Collapsible.Root>
    <Collapsible.Trigger class="flex w-full items-center justify-between">
      <h4 class="text-xs font-medium tracking-wide text-fg-muted uppercase">Commands</h4>
      <ChevronDown
        class="h-3.5 w-3.5 -rotate-90 text-fg-muted/60 transition-transform duration-200 [[data-state=open]>&]:rotate-0"
      />
    </Collapsible.Trigger>
    <Collapsible.Content class="pt-1">
      <div class="grid gap-1">
        {#each commandNames as name (name)}
          <CommandButton {device} commandName={name} />
        {/each}
      </div>
    </Collapsible.Content>
  </Collapsible.Root>
{/if}
