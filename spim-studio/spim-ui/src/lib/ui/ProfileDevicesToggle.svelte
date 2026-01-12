<script lang="ts">
	import { ToggleGroup, Checkbox, Collapsible } from 'bits-ui';
	import Icon from '@iconify/svelte';
	import type { App } from '$lib/app';
	import type { SpimRigConfig, ChannelConfig } from '$lib/core/config';
	import { SvelteMap, SvelteSet } from 'svelte/reactivity';

	interface Props {
		app: App;
		visible?: Set<string>;
		colors?: Record<string, string>; // Optional color map for device indicators
		waveformsOnly?: boolean; // Optional: filter to show only devices with waveforms (those with acq_port in DAQ config)
	}

	let { app, visible = $bindable(new Set<string>()), colors, waveformsOnly = false }: Props = $props();

	type GroupMode = 'none' | 'type' | 'path' | 'channel';

	interface DeviceGroup {
		id: string;
		label: string;
		devices: string[];
	}

	let groupMode = $state<GroupMode>('none');

	// Get active profile and its config
	const activeProfile = $derived(app.activeProfile);
	const config = $derived(app.config);

	// Get set of devices with waveforms (those with acq_port in DAQ config)
	const devicesWithWaveforms = $derived.by(() => {
		if (!config?.daq?.acq_ports) return new Set<string>();
		return new Set(Object.keys(config.daq.acq_ports));
	});

	// Helper to check if device is a filter wheel
	function isFilterWheel(config: SpimRigConfig, deviceId: string): boolean {
		// Check all detection paths for filter wheels
		for (const detectionPath of Object.values(config.detection)) {
			if (detectionPath.filter_wheels.includes(deviceId)) {
				return true;
			}
		}
		return false;
	}

	// Build device groups based on mode
	const groups = $derived.by(() => {
		if (!activeProfile || !config) return [];

		switch (groupMode) {
			case 'none':
				return buildGroupsFlat(config, activeProfile.channels);
			case 'type':
				return buildGroupsByType(config, activeProfile.channels);
			case 'path':
				return buildGroupsByPath(config, activeProfile.channels);
			case 'channel':
				return buildGroupsByChannel(config, activeProfile.channels);
			default:
				return [];
		}
	});

	// Initialize visible set with all devices when profile changes
	$effect(() => {
		if (groups.length > 0) {
			const allDevices = new SvelteSet<string>();
			groups.forEach((group) => group.devices.forEach((d) => allDevices.add(d)));
			visible = allDevices;
		}
	});

	// Build flat list (no grouping)
	function buildGroupsFlat(config: SpimRigConfig, channels: Record<string, ChannelConfig>): DeviceGroup[] {
		const profileDevices = new SvelteSet<string>();
		Object.values(channels).forEach((channel) => {
			profileDevices.add(channel.detection);
			profileDevices.add(channel.illumination);
			Object.keys(channel.filters).forEach((fw) => profileDevices.add(fw));
		});

		let devices = Array.from(profileDevices).sort();

		// Filter to only devices with waveforms if specified
		if (waveformsOnly) {
			devices = devices.filter((d) => devicesWithWaveforms.has(d));
		}

		return [
			{
				id: 'all',
				label: 'All Devices',
				devices
			}
		];
	}

	// Build groups by device type
	function buildGroupsByType(config: SpimRigConfig, channels: Record<string, ChannelConfig>): DeviceGroup[] {
		const devicesByType = new SvelteMap<string, Set<string>>();

		// Get all devices used by this profile's channels
		const profileDevices = new SvelteSet<string>();
		Object.values(channels).forEach((channel) => {
			profileDevices.add(channel.detection); // camera
			profileDevices.add(channel.illumination); // laser
			Object.keys(channel.filters).forEach((fw) => profileDevices.add(fw)); // filter wheels
		});

		// Categorize devices by type
		profileDevices.forEach((deviceId) => {
			// Filter to only devices with waveforms if specified
			if (waveformsOnly && !devicesWithWaveforms.has(deviceId)) {
				return;
			}

			let type = 'Other';

			if (deviceId in config.detection) {
				type = 'Cameras';
			} else if (deviceId in config.illumination) {
				type = 'Lasers';
			} else if (isFilterWheel(config, deviceId)) {
				type = 'Filter Wheels';
			} else if (config.stage) {
				const stageDevices = [
					config.stage.x,
					config.stage.y,
					config.stage.z,
					config.stage.roll,
					config.stage.pitch,
					config.stage.yaw
				].filter(Boolean);
				if (stageDevices.includes(deviceId)) {
					type = 'Stage Axes';
				}
			}

			if (!devicesByType.has(type)) {
				devicesByType.set(type, new Set());
			}
			devicesByType.get(type)!.add(deviceId);
		});

		// Convert to DeviceGroup array
		return Array.from(devicesByType.entries()).map(([type, devices]) => ({
			id: type.toLowerCase().replace(/\s+/g, '_'),
			label: type,
			devices: Array.from(devices).sort()
		}));
	}

	// Build groups by optical path (detection vs illumination)
	function buildGroupsByPath(config: SpimRigConfig, channels: Record<string, ChannelConfig>): DeviceGroup[] {
		const detectionDevices = new SvelteSet<string>();
		const illuminationDevices = new SvelteSet<string>();

		Object.values(channels).forEach((channel) => {
			// Detection: camera + filter wheels
			detectionDevices.add(channel.detection);
			Object.keys(channel.filters).forEach((fw) => detectionDevices.add(fw));

			// Illumination: laser
			illuminationDevices.add(channel.illumination);
		});

		let detectionList = Array.from(detectionDevices).sort();
		let illuminationList = Array.from(illuminationDevices).sort();

		// Filter to only devices with waveforms if specified
		if (waveformsOnly) {
			detectionList = detectionList.filter((d) => devicesWithWaveforms.has(d));
			illuminationList = illuminationList.filter((d) => devicesWithWaveforms.has(d));
		}

		return [
			{
				id: 'detection',
				label: 'Detection',
				devices: detectionList
			},
			{
				id: 'illumination',
				label: 'Illumination',
				devices: illuminationList
			}
		];
	}

	// Build groups by channel
	function buildGroupsByChannel(config: SpimRigConfig, channels: Record<string, ChannelConfig>): DeviceGroup[] {
		return Object.entries(channels).map(([channelId, channel]) => {
			const devices = new SvelteSet<string>();
			devices.add(channel.detection);
			devices.add(channel.illumination);
			Object.keys(channel.filters).forEach((fw) => devices.add(fw));

			let deviceList = Array.from(devices).sort();

			// Filter to only devices with waveforms if specified
			if (waveformsOnly) {
				deviceList = deviceList.filter((d) => devicesWithWaveforms.has(d));
			}

			return {
				id: channelId,
				label: channel.label || channelId,
				devices: deviceList
			};
		});
	}

	// Calculate three-state checkbox state for a group
	function getGroupCheckState(group: DeviceGroup): { checked: boolean; indeterminate: boolean } {
		const visibleInGroup = group.devices.filter((d) => visible.has(d)).length;

		if (visibleInGroup === 0) return { checked: false, indeterminate: false };
		if (visibleInGroup === group.devices.length) return { checked: true, indeterminate: false };
		return { checked: false, indeterminate: true };
	}

	// Get count of visible devices in group
	function getVisibleCount(group: DeviceGroup): number {
		return group.devices.filter((d) => visible.has(d)).length;
	}

	// Toggle entire group
	function toggleGroup(group: DeviceGroup, checked: boolean) {
		const newVisible = new SvelteSet(visible);

		if (checked) {
			// Check all
			group.devices.forEach((d) => newVisible.add(d));
		} else {
			// Uncheck all
			group.devices.forEach((d) => newVisible.delete(d));
		}

		visible = newVisible;
	}

	// Toggle individual device
	function toggleDevice(deviceId: string, checked: boolean) {
		const newVisible = new SvelteSet(visible);

		if (checked) {
			newVisible.add(deviceId);
		} else {
			newVisible.delete(deviceId);
		}

		visible = newVisible;
	}
</script>

<div class="flex flex-col gap-2">
	<!-- Mode Toggle -->
	<div class="flex items-center gap-1.5">
		<ToggleGroup.Root type="single" bind:value={groupMode} class="inline-flex rounded border border-zinc-700">
			<ToggleGroup.Item
				value="none"
				class="px-2 py-0.5 text-xs transition-colors hover:bg-zinc-800 data-[state=on]:bg-zinc-700 data-[state=on]:text-zinc-100"
			>
				All
			</ToggleGroup.Item>
			<ToggleGroup.Item
				value="type"
				class="border-x border-zinc-700 px-2 py-0.5 text-xs transition-colors hover:bg-zinc-800 data-[state=on]:bg-zinc-700 data-[state=on]:text-zinc-100"
			>
				Type
			</ToggleGroup.Item>
			<ToggleGroup.Item
				value="path"
				class="border-x border-zinc-700 px-2 py-0.5 text-xs transition-colors hover:bg-zinc-800 data-[state=on]:bg-zinc-700 data-[state=on]:text-zinc-100"
			>
				Path
			</ToggleGroup.Item>
			<ToggleGroup.Item
				value="channel"
				class="px-2 py-0.5 text-xs transition-colors hover:bg-zinc-800 data-[state=on]:bg-zinc-700 data-[state=on]:text-zinc-100"
			>
				Channel
			</ToggleGroup.Item>
		</ToggleGroup.Root>
	</div>

	<!-- Device Tree -->
	<div class="mt-3 space-y-4">
		{#if groups.length === 0}
			<p class="text-xs text-zinc-500">No devices available</p>
		{:else}
			{#each groups as group (group.id)}
				{@const groupState = getGroupCheckState(group)}
				<Collapsible.Root open={true}>
					<div class="flex items-start gap-0.5">
						<!-- Group Checkbox -->
						<Checkbox.Root
							checked={groupState.checked}
							indeterminate={groupState.indeterminate}
							onCheckedChange={(checked) => toggleGroup(group, checked ?? false)}
							class="mt-0 flex h-3.5 w-3.5 items-center justify-center rounded border border-zinc-600 bg-zinc-800 transition-colors data-[state=checked]:border-emerald-500 data-[state=checked]:bg-emerald-600"
						>
							{#if groupState.checked}
								<Icon icon="mdi:check" class="text-white" width="12" height="12" />
							{:else if groupState.indeterminate}
								<Icon icon="mdi:minus" class="text-white" width="12" height="12" />
							{/if}
						</Checkbox.Root>

						<!-- Group Label + Expand/Collapse -->
						<Collapsible.Trigger class="flex flex-1 items-center gap-1 text-xs font-medium hover:text-zinc-300">
							<Icon
								icon="mdi:chevron-right"
								class="text-zinc-500 transition-transform data-[state=open]:rotate-90"
								width="14"
								height="14"
							/>
							<span>
								{group.label}
								<span class="text-zinc-500">({getVisibleCount(group)}/{group.devices.length})</span>
							</span>
						</Collapsible.Trigger>
					</div>

					<!-- Child Devices -->
					<Collapsible.Content class="mt-3 ml-3.5 space-y-2">
						{#each group.devices as deviceId (deviceId)}
							<label class="flex cursor-pointer items-center gap-2 hover:text-zinc-300">
								<Checkbox.Root
									checked={visible.has(deviceId)}
									onCheckedChange={(checked) => toggleDevice(deviceId, checked ?? false)}
									class="flex h-3 w-3 items-center justify-center rounded border border-zinc-600 bg-zinc-800 transition-colors data-[state=checked]:border-emerald-500 data-[state=checked]:bg-emerald-600"
								>
									{#if visible.has(deviceId)}
										<Icon icon="mdi:check" class="text-white" width="10" height="10" />
									{/if}
								</Checkbox.Root>
								<span class="text-xs">{deviceId}</span>
								{#if colors && colors[deviceId]}
									<div class="ml-auto h-1.5 w-1.5 rounded-full" style="background-color: {colors[deviceId]};"></div>
								{/if}
							</label>
						{/each}
					</Collapsible.Content>
				</Collapsible.Root>
			{/each}
		{/if}
	</div>
</div>
