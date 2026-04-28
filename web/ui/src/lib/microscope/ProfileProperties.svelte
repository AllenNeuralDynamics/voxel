<script lang="ts">
  import type { Microscope } from '$lib/microscope';
  import { discoverProfileDevices, isFilterWheel } from './profile';
  import { isPropDiverged, formatPropValue, decimalsFromStep } from './device';
  import { BoolModel, EnumeratedModel, NumericModel } from '$lib/prop.svelte';
  import { Collapsible } from 'bits-ui';
  import { ChevronRight, Restore } from '$lib/icons';
  import { Button, SpinBox, Select, Switch } from '$lib/kit';
  import { sanitizeString } from '$lib/utils';

  interface Props {
    microscope: Microscope;
    profileId: string;
  }

  let { microscope, profileId }: Props = $props();

  const profile = $derived(microscope.config.profiles[profileId]);

  /** All profile devices excluding filter wheels, sorted by role. */
  const devices = $derived(
    discoverProfileDevices(microscope.config, profileId).filter((d) => !isFilterWheel(microscope.config, d.id))
  );

  const groups = $derived(
    (
      [
        { label: 'Other Devices', devices: devices.filter((d) => d.role !== 'camera' && d.role !== 'laser') },
        { label: 'Cameras', devices: devices.filter((d) => d.role === 'camera') },
        { label: 'Lasers', devices: devices.filter((d) => d.role === 'laser') }
      ] as { label: string; devices: typeof devices }[]
    ).filter((g) => g.devices.length > 0)
  );

  const isActiveProfile = $derived(profileId === microscope.profiles.activeId);

  /** Per-device setup commands open state. */
  let setupOpen: Record<string, boolean> = $state({});

  function hasDivergence(deviceId: string, savedProps: Record<string, unknown> | undefined): boolean {
    if (!savedProps) return false;
    const device = microscope.get(deviceId);
    if (!device) return false;
    for (const [propName, savedValue] of Object.entries(savedProps)) {
      if (isPropDiverged(savedValue, device.getProp(propName)?.value)) return true;
    }
    return false;
  }
</script>

{#if profile}
  <div class="space-y-4">
    {#each groups as group (group)}
      <div>
        <div class="mb-2 flex items-center justify-between">
          <span class="text-xs font-medium tracking-wide text-fg-muted uppercase">{group.label}</span>
          {#if isActiveProfile}
            <Button
              variant="ghost"
              size="xs"
              class="text-fg-faint"
              onclick={() => {
                for (const d of group.devices) microscope.profiles.saveProps(d.id);
              }}
            >
              Save All
            </Button>
          {/if}
        </div>
        <div class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] items-start gap-3">
          {#each group.devices as { id: deviceId } (deviceId)}
            {@const device = microscope.get(deviceId)}
            {@const savedProps = profile.props?.[deviceId]}
            {@const setupCommands = profile.setup?.[deviceId]}

            {@const rwProperties = (() => {
              const props = device?.interface?.properties;
              if (!props) return [];
              return Object.entries(props)
                .filter(([, info]) => info.access === 'rw')
                .sort(([a], [b]) => a.localeCompare(b));
            })()}

            {@const hasContent = rwProperties.length > 0 || (savedProps != null && Object.keys(savedProps).length > 0)}

            {#if hasContent}
              <div class="rounded-lg border border-border p-3">
                <!-- Card header -->
                <div class="mb-2.5 flex items-center justify-between">
                  <span class="text-sm font-medium text-fg">{sanitizeString(deviceId)}</span>
                  {#if isActiveProfile}
                    <div class="flex items-center gap-1">
                      {#if hasDivergence(deviceId, savedProps)}
                        <Button
                          variant="ghost"
                          size="icon-xs"
                          onclick={() => microscope.profiles.applyProps([deviceId])}
                          title="Revert to saved"
                        >
                          <Restore width="14" height="14" />
                        </Button>
                      {/if}
                      <Button variant="outline" size="xs" onclick={() => microscope.profiles.saveProps(deviceId)}>
                        Save
                      </Button>
                    </div>
                  {/if}
                </div>

                <!-- Properties -->
                <div class="space-y-1.5">
                  {#each rwProperties as [propName, propInfo] (propName)}
                    {@const saved = savedProps?.[propName]}
                    {@const model = device?.getProp(propName)}
                    {@const current = model?.value}
                    {@const propDiverged = isPropDiverged(saved, current)}
                    {@const hasSaved = saved !== undefined && saved !== null}
                    {@const stepHint = model instanceof NumericModel ? model.step : null}

                    <div>
                      <div class="flex items-center justify-between gap-3">
                        <div class="flex items-center gap-1 text-xs text-fg-muted">
                          <span class="min-w-0 shrink truncate" title={propInfo.desc || propInfo.label || propName}>
                            {propInfo.label || propName}
                          </span>
                          {#if propInfo.units}
                            <span class="opacity-50">({propInfo.units})</span>
                          {/if}
                          {#if propDiverged}
                            <span class="text-warning opacity-90">({formatPropValue(saved, stepHint)})</span>
                          {/if}
                          {#if !hasSaved}
                            <span class="inline-block size-1 rounded-full bg-warning opacity-70"></span>
                          {/if}
                        </div>

                        <div class="w-40 shrink-0">
                          {#if isActiveProfile && model}
                            {#if model instanceof EnumeratedModel}
                              <Select
                                size="xs"
                                class="w-full"
                                value={String(current ?? '')}
                                options={model.options.map((o) => ({
                                  value: String(o),
                                  label: String(o)
                                }))}
                                onchange={(v) => {
                                  const numericOptions = model.options.some((o) => typeof o === 'number');
                                  model.patch((numericOptions ? Number(v) : v) as never);
                                }}
                              />
                            {:else if model instanceof BoolModel}
                              <div class="flex justify-end">
                                <Switch
                                  size="sm"
                                  checked={model.value === true}
                                  onCheckedChange={(v) => model.patch(v)}
                                />
                              </div>
                            {:else if model instanceof NumericModel}
                              <SpinBox
                                size="xs"
                                appearance="bordered"
                                class="w-full"
                                value={model.value ?? 0}
                                min={model.min ?? -Infinity}
                                max={model.max ?? Infinity}
                                step={model.step ?? 1}
                                decimals={decimalsFromStep(model.step)}
                                numCharacters={6}
                                onChange={(v) => model.patch(v)}
                              />
                            {:else}
                              <span class="block text-right font-mono text-xs text-fg">
                                {formatPropValue(current, stepHint)}
                              </span>
                            {/if}
                          {:else}
                            <span
                              class="block text-right font-mono text-xs {current != null
                                ? 'text-fg'
                                : 'text-fg-muted/40'}"
                            >
                              {formatPropValue(current, stepHint)}
                            </span>
                          {/if}
                        </div>
                      </div>
                    </div>
                  {/each}
                </div>

                <!-- Setup commands -->
                {#if setupCommands && setupCommands.length > 0}
                  <div class="mt-3 border-t border-border pt-2">
                    <Collapsible.Root
                      open={setupOpen[deviceId] ?? false}
                      onOpenChange={(open) => {
                        setupOpen = { ...setupOpen, [deviceId]: open };
                      }}
                    >
                      <Collapsible.Trigger class="flex items-center gap-1 text-xs text-fg-muted hover:text-fg">
                        <ChevronRight
                          width="12"
                          height="12"
                          class="shrink-0 transition-transform {setupOpen[deviceId] ? 'rotate-90' : ''}"
                        />
                        <span>Setup Commands ({setupCommands.length})</span>
                      </Collapsible.Trigger>
                      <Collapsible.Content class="mt-1 space-y-0.5 pl-4">
                        {#each setupCommands as cmd, i (i)}
                          <div class="font-mono text-xs text-fg-muted">
                            <span class="text-fg">{cmd.attr}</span>
                            {#if cmd.kwargs && Object.keys(cmd.kwargs).length > 0}
                              <span class="text-fg-muted/60">
                                ({Object.entries(cmd.kwargs)
                                  .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                                  .join(', ')})
                              </span>
                            {/if}
                          </div>
                        {/each}
                      </Collapsible.Content>
                    </Collapsible.Root>
                  </div>
                {/if}
              </div>
            {/if}
          {/each}
        </div>
      </div>
    {/each}
  </div>
{/if}
