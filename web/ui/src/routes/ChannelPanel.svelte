<script lang="ts">
	import { ToggleGroup, Tooltip } from 'bits-ui';
	import Icon from '@iconify/svelte';
	import LaserControl from '$lib/ui/devices/LaserControl.svelte';
	import CameraControl from '$lib/ui/devices/CameraControl.svelte';
	import type { Session, ChannelConfig } from '$lib/main';

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

{#snippet channelInfoTooltip(name: string, label: string | null | undefined, config: ChannelConfig | undefined)}
	{@const filterEntries = config?.filters ? Object.entries(config.filters) : []}
	<Tooltip.Provider>
		<Tooltip.Root delayDuration={150}>
			<Tooltip.Trigger
				class="flex items-center rounded p-1 text-zinc-300 transition-colors hover:bg-zinc-800"
				aria-label="Channel info"
			>
				<Icon icon="mdi:information-outline" width="14" height="14" />
			</Tooltip.Trigger>
			<Tooltip.Content
				class="z-50 w-64 rounded-md border border-zinc-700 bg-zinc-900 p-3 text-left text-xs text-zinc-200 shadow-xl outline-none"
				sideOffset={4}
				align="end"
			>
				<div class="space-y-2">
					<div>
						<p class="text-sm font-semibold text-zinc-100">
							{label ?? name}
						</p>
						<p class="mt-1 text-xs text-zinc-300">
							{config?.desc ?? 'No description available.'}
						</p>
					</div>
					{#if config?.illumination || filterEntries.length || config?.detection}
						<div class="space-y-1 border-t border-zinc-800 pt-2 text-[0.7rem] text-zinc-300">
							{#if config?.illumination}
								<div class="flex justify-between gap-2">
									<span class="text-zinc-400">Illumination</span>
									<span class="text-right text-zinc-200">{config.illumination}</span>
								</div>
							{/if}
							{#if config?.detection}
								<div class="flex justify-between gap-2">
									<span class="text-zinc-400">Detection</span>
									<span class="text-right text-zinc-200">{config.detection}</span>
								</div>
							{/if}
							{#if config?.emission}
								<div class="flex justify-between gap-2">
									<span class="text-zinc-400">Emission</span>
									<span class="text-right text-zinc-200">{config.emission} nm</span>
								</div>
							{/if}
							{#if filterEntries.length}
								<div class="space-y-1">
									<div class="mb-1 border-b border-zinc-800 pt-1 text-zinc-500/90">Filters</div>
									<div class="space-y-1">
										{#each filterEntries as [filterName, filterValue] (filterName)}
											<div class="flex justify-between gap-2">
												<span class="text-zinc-400">{filterName}:</span>
												<span class="text-right text-zinc-200">{filterValue}</span>
											</div>
										{/each}
									</div>
								</div>
							{/if}
						</div>
					{/if}
				</div>
			</Tooltip.Content>
		</Tooltip.Root>
	</Tooltip.Provider>
{/snippet}

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

{#if session.preview.channels.length === 0}
	<div class="flex flex-1 items-center justify-center p-4">
		<p class="text-sm text-muted-foreground">No channels available</p>
	</div>
{:else}
	<div class="flex flex-1 flex-col overflow-y-auto">
		{#each session.preview.channels as channel (channel.idx)}
			{#if channel.name}
				<div class="space-y-4 px-4 py-4">
					<div class="-mt-2 flex items-center justify-between">
						<span class="text-xs font-medium text-zinc-200">
							{channel.label ?? channel.config?.label ?? channel.name}
						</span>
						{@render channelInfoTooltip(channel.name, channel.label, channel.config)}
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
