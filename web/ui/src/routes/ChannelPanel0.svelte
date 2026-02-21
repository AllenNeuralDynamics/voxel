<script lang="ts">
	import { ToggleGroup } from 'bits-ui';
	import ChannelInfoTooltip from '$lib/ui/ChannelInfoTooltip.svelte';
	import LaserControl from '$lib/ui/devices/LaserControl.svelte';
	import CameraControl from '$lib/ui/devices/CameraControl.svelte';
	import type { Session } from '$lib/main';

	type DeviceFilter = 'all' | 'detection' | 'illumination' | 'summary';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	let deviceFilter = $state<DeviceFilter>('all');

	const showIllumination = $derived(deviceFilter === 'all' || deviceFilter === 'illumination');
	const showDetection = $derived(deviceFilter === 'all' || deviceFilter === 'detection');

	const filterItems: { value: DeviceFilter; label: string }[] = [
		{ value: 'all', label: 'All Devices' },
		{ value: 'detection', label: 'Detection' },
		{ value: 'illumination', label: 'Illumination' },
		{ value: 'summary', label: 'Summary' }
	];
</script>

{#snippet deviceFilterToggle()}
	<ToggleGroup.Root
		type="single"
		value={deviceFilter}
		onValueChange={(v) => (deviceFilter = v as DeviceFilter)}
		class="flex justify-between gap-1 rounded-lg bg-zinc-900/70 py-1"
	>
		{#each filterItems as item (item.value)}
			<ToggleGroup.Item
				value={item.value}
				class="flex-1 rounded px-1.5 py-1.5 text-center text-[0.7rem] font-medium transition-colors data-[state=off]:text-zinc-400 data-[state=off]:hover:text-zinc-300 data-[state=on]:bg-zinc-700 data-[state=on]:text-zinc-100"
			>
				{item.label}
			</ToggleGroup.Item>
		{/each}
	</ToggleGroup.Root>
{/snippet}

<div class="px-4 py-3">
	{@render deviceFilterToggle()}
</div>

{#if session.previewState.channels.length === 0}
	<div class="flex flex-1 items-center justify-center p-4">
		<p class="text-sm text-muted-foreground">No channels available</p>
	</div>
{:else}
	<div class="flex flex-1 flex-col overflow-y-auto">
		{#each session.previewState.channels as channel (channel.idx)}
			{#if channel.name}
				<div class="space-y-4 px-4 py-4">
					<div class="-mt-2 flex items-center justify-between">
						<span class="text-xs font-medium text-zinc-200">
							{channel.label ?? channel.config?.label ?? channel.name}
						</span>
						<ChannelInfoTooltip name={channel.name} label={channel.label} config={channel.config} />
					</div>

					{#if channel.config?.illumination}
						<LaserControl
							deviceId={channel.config.illumination}
							devicesManager={session.devices}
							collapsed={!showIllumination}
						/>
					{/if}

					{#if channel.config?.detection}
						<CameraControl
							deviceId={channel.config.detection}
							devicesManager={session.devices}
							collapsed={!showDetection}
						/>
					{/if}
				</div>
				<div class="border-t border-border"></div>
			{/if}
		{/each}
	</div>
{/if}
