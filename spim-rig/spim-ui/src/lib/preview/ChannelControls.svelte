<script lang="ts">
	import ColorPicker from '$lib/ui/ColorPicker.svelte';
	import { Tooltip } from 'bits-ui';
	import Histogram from './Histogram.svelte';
	import Icon from '@iconify/svelte';
	import { COLORMAP_COLORS } from './colormap';
	import type { Previewer, PreviewChannel } from './previewer.svelte';

	interface Props {
		channel: PreviewChannel;
		previewer: Previewer;
	}

	let { channel, previewer }: Props = $props();

	// Get preset colors for the color picker
	const presetColors = Object.values(COLORMAP_COLORS);
	const filterEntries = $derived<[string, string][]>(
		channel.config?.filters ? Object.entries(channel.config.filters) : []
	);

	function handleColorChange(newColor: string) {
		channel.setColor(newColor);
	}

	function handleVisibilityToggle() {
		channel.visible = !channel.visible;
	}

	function handleLevelsChange(min: number, max: number) {
		if (channel.name) {
			previewer.setChannelLevels(channel.name, min, max);
		}
	}
</script>

<div class="space-y-2">
	<!-- Channel name and controls -->
	<div class="flex items-center justify-between">
		<span class="font-medium">{channel.label ?? channel.config?.label ?? 'Unknown'}</span>
		<div class="flex items-center gap-2">
			<Tooltip.Provider>
				<Tooltip.Root delayDuration={150}>
					<Tooltip.Trigger
						class="flex items-center rounded p-1 text-zinc-400 transition-colors hover:bg-zinc-800"
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
									{channel.label ?? channel.name ?? 'Channel'}
								</p>
								<p class="mt-1 text-xs text-zinc-300">
									{channel.config?.desc ?? 'No description available.'}
								</p>
							</div>
							{#if channel.config?.illumination || filterEntries.length || channel.config?.detection}
								<div class="space-y-1 border-t border-zinc-800 pt-2 text-[0.7rem] text-zinc-300">
									{#if channel.config?.illumination}
										<div class="flex justify-between gap-2">
											<span class="text-zinc-400">Illumination</span>
											<span class="text-right text-zinc-200">{channel.config.illumination}</span>
										</div>
									{/if}
									{#if channel.config?.detection}
										<div class="flex justify-between gap-2">
											<span class="text-zinc-400">Detection</span>
											<span class="text-right text-zinc-200">{channel.config.detection}</span>
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
			<button
				onclick={handleVisibilityToggle}
				class="flex items-center rounded p-1 transition-colors {channel.visible
					? 'text-zinc-400 hover:bg-zinc-800'
					: 'text-zinc-600 hover:bg-zinc-800'}"
				aria-label={channel.visible ? 'Hide channel' : 'Show channel'}
			>
				<Icon icon={channel.visible ? 'mdi:eye' : 'mdi:eye-off'} width="14" height="14" />
			</button>
			<ColorPicker color={channel.color} {presetColors} onColorChange={handleColorChange} align="end" />
		</div>
	</div>

	<Histogram
		histData={channel.latestHistogram}
		levelsMin={channel.levelsMin}
		levelsMax={channel.levelsMax}
		dataTypeMax={65535}
		color={channel.color}
		onLevelsChange={handleLevelsChange}
	/>
</div>
