<script lang="ts">
	import type { DevicesManager, PropertyInfo } from '$lib/main';
	import { ChevronDown } from '$lib/icons';
	import { Collapsible } from '$lib/ui/kit';
	import PropertyControl from './PropertyControl.svelte';
	import CommandButton from './CommandButton.svelte';
	import { isStructuredValue, type DeviceExclusions } from './utils';

	interface Props {
		deviceId: string;
		devicesManager: DevicesManager;
		exclusions?: DeviceExclusions;
		size?: 'sm' | 'md';
	}

	let { deviceId, devicesManager, exclusions, size = 'sm' }: Props = $props();

	let excludeProps = $derived(new Set(exclusions?.props ?? []));
	let excludeCmds = $derived(new Set(exclusions?.cmds ?? []));

	let device = $derived(devicesManager.getDevice(deviceId));

	// --- Properties ---

	let filteredProperties = $derived.by(() => {
		const props = device?.interface?.properties;
		if (!props) return { rw: [] as Array<[string, PropertyInfo]>, ro: [] as Array<[string, PropertyInfo]> };

		const entries = Object.entries(props).filter(([name]) => !excludeProps.has(name));

		// Split: scalar rw → controls, everything else → status
		// Structured rw values are read-only in practice (tree view can't edit), so they join ro.
		const rw = entries.filter(
			([name, info]) =>
				info.access === 'rw' && !isStructuredValue(devicesManager.getPropertyModel(deviceId, name)?.value)
		);
		const ro = entries.filter(
			([name, info]) =>
				info.access === 'ro' ||
				(info.access === 'rw' && isStructuredValue(devicesManager.getPropertyModel(deviceId, name)?.value))
		);

		return { rw, ro };
	});

	let showRw = $derived(filteredProperties.rw.length > 0);
	let showRo = $derived(filteredProperties.ro.length > 0);

	function isStructuredProp(name: string): boolean {
		return isStructuredValue(devicesManager.getPropertyModel(deviceId, name)?.value);
	}

	// --- Commands ---

	let commandNames = $derived.by(() => {
		const cmds = device?.interface?.commands;
		if (!cmds) return [] as string[];
		return Object.keys(cmds).filter((n) => !excludeCmds.has(n));
	});

	let showCmds = $derived(commandNames.length > 0);
</script>

{#if showRw}
	<div class="grid gap-2">
		{#each filteredProperties.rw as [name, info] (name)}
			<div class="flex items-center justify-between gap-4">
				<span class="text-fg shrink-0 text-sm" title={info.desc ?? ''}>
					{info.label}
				</span>
				<div class="max-w-64 min-w-0">
					<PropertyControl {deviceId} propName={name} {devicesManager} {size} />
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
						<span class="text-fg-muted text-sm">{info.label}</span>
						<ChevronDown
							class="text-fg-muted/60 h-3.5 w-3.5 -rotate-90 transition-transform duration-200 [[data-state=open]>&]:rotate-0"
						/>
					</Collapsible.Trigger>
					<Collapsible.Content class="pt-1">
						<div class="rounded border border-border bg-card p-2">
							<PropertyControl {deviceId} propName={name} {devicesManager} {size} />
						</div>
					</Collapsible.Content>
				</Collapsible.Root>
			{:else}
				<div class="flex min-h-5 items-baseline justify-between gap-4">
					<span class="text-fg-muted shrink-0 text-sm" title={info.desc ?? ''}>
						{info.label}
					</span>
					<PropertyControl {deviceId} propName={name} {devicesManager} {size} />
				</div>
			{/if}
		{/each}
	</div>
{/if}

{#if showCmds}
	<Collapsible.Root>
		<Collapsible.Trigger class="flex w-full items-center justify-between">
			<h4 class="text-fg-muted text-xs font-medium tracking-wide uppercase">Commands</h4>
			<ChevronDown
				class="text-fg-muted/60 h-3.5 w-3.5 -rotate-90 transition-transform duration-200 [[data-state=open]>&]:rotate-0"
			/>
		</Collapsible.Trigger>
		<Collapsible.Content class="pt-1">
			<div class="grid gap-1">
				{#each commandNames as name (name)}
					<CommandButton {deviceId} commandName={name} {devicesManager} />
				{/each}
			</div>
		</Collapsible.Content>
	</Collapsible.Root>
{/if}
