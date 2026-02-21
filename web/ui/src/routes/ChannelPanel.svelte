<script lang="ts">
	import { ToggleGroup } from 'bits-ui';
	import ChannelInfoTooltip from '$lib/ui/ChannelInfoTooltip.svelte';
	import LaserControl from '$lib/ui/devices/LaserControl.svelte';
	import CameraControl from '$lib/ui/devices/CameraControl.svelte';
	import type { Session } from '$lib/main';

	type DeviceGroup = 'detection' | 'illumination';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	let activeGroups = $state<DeviceGroup[]>(['detection', 'illumination']);

	const showIllumination = $derived(activeGroups.includes('illumination'));
	const showDetection = $derived(activeGroups.includes('detection'));

	const groupItems: { value: DeviceGroup; label: string }[] = [
		{ value: 'detection', label: 'Detection' },
		{ value: 'illumination', label: 'Illumination' }
	];
</script>

{#snippet deviceGroupToggle()}
	<ToggleGroup.Root
		type="multiple"
		value={activeGroups}
		onValueChange={(v) => (activeGroups = v as DeviceGroup[])}
		class="flex gap-1.5"
	>
		{#each groupItems as item (item.value)}
			<ToggleGroup.Item
				value={item.value}
				class="rounded-full border px-2.5 py-1 text-[0.7rem] font-medium transition-colors data-[state=off]:border-zinc-700 data-[state=off]:text-zinc-500 data-[state=off]:hover:border-zinc-600 data-[state=off]:hover:text-zinc-400 data-[state=on]:border-zinc-500 data-[state=on]:bg-zinc-800 data-[state=on]:text-zinc-200"
			>
				{item.label}
			</ToggleGroup.Item>
		{/each}
	</ToggleGroup.Root>
{/snippet}

<div class="px-4 py-3">
	{@render deviceGroupToggle()}
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
