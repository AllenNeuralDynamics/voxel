<script lang="ts">
	import { Popover } from 'bits-ui';
	import { isValidHex } from '$lib/utils';
	import type { ColormapCatalog } from '$lib/core';

	interface Props {
		/** Display label for the channel (shown as trigger text) */
		label: string;
		/** Current colormap name or hex color */
		colormap: string | null;
		/** Catalog of colormap groups */
		catalog: ColormapCatalog;
		/** Callback when user picks a colormap */
		onColormapChange: (colormap: string) => void;
	}

	let { label, colormap, catalog, onColormapChange }: Props = $props();

	let customHexInput = $state('');
	let popoverOpen = $state(false);

	function stopsToGradient(stops: string[]): string {
		return `linear-gradient(to right, ${stops.join(', ')})`;
	}

	/** Get the display color for the trigger text from the active colormap. */
	function getTriggerColor(cmap: string | null, cat: ColormapCatalog): string {
		if (!cmap) return '#ffffff';
		for (const group of cat) {
			const stops = group.colormaps[cmap];
			if (stops) return stops[stops.length - 1];
		}
		return cmap.startsWith('#') ? cmap : '#ffffff';
	}

	const triggerColor = $derived(getTriggerColor(colormap, catalog));

	function handleSwatchClick(name: string) {
		onColormapChange(name);
		popoverOpen = false;
	}

	function handleCustomHexSubmit() {
		const hex = customHexInput.trim();
		if (isValidHex(hex)) {
			onColormapChange(hex);
			customHexInput = '';
			popoverOpen = false;
		}
	}

	function handleCustomHexKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			handleCustomHexSubmit();
		}
	}
</script>

<Popover.Root bind:open={popoverOpen}>
	<Popover.Trigger
		style="all: unset; cursor: pointer; font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; color: {triggerColor}; border-bottom: 1px solid transparent;"
		aria-label="Pick colormap for {label}"
	>
		{label}
	</Popover.Trigger>

	<Popover.Content
		class="z-50 w-64 rounded-md border border-zinc-700 bg-zinc-900 shadow-xl outline-none"
		sideOffset={4}
		align="start"
	>
		<div class="max-h-80 overflow-y-auto">
			{#each catalog as group (group.uid)}
				<details class="group-section">
					<summary class="group-header">
						<span class="chevron">&#9654;</span>
						{group.label}
					</summary>
					<div class="grid grid-cols-4 gap-1.5 px-3 pb-2">
						{#each Object.entries(group.colormaps) as [name, stops] (name)}
							<button
								type="button"
								onclick={() => handleSwatchClick(name)}
								class="swatch {colormap === name ? 'selected' : ''}"
								style="background: {stopsToGradient(stops)}"
								title={name}
								aria-label="Select colormap {name}"
							></button>
						{/each}
					</div>
				</details>
			{/each}
		</div>

		<!-- Custom hex input -->
		<div class="border-t border-zinc-700 px-3 py-2">
			<div class="flex gap-1.5">
				<input
					type="text"
					bind:value={customHexInput}
					onkeydown={handleCustomHexKeydown}
					placeholder="#ff00ff"
					size="7"
					class="h-6 min-w-0 flex-1 rounded border border-zinc-600 bg-zinc-800 px-1.5 font-mono text-[0.65rem] text-zinc-200 placeholder-zinc-500 focus:border-zinc-400 focus:outline-none"
				/>
				<button
					type="button"
					onclick={handleCustomHexSubmit}
					class="h-6 rounded border border-zinc-600 bg-zinc-800 px-2 text-[0.6rem] text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-zinc-200"
				>
					Apply
				</button>
			</div>
		</div>
	</Popover.Content>
</Popover.Root>

<style>
	.group-section {
		border-bottom: 1px solid rgb(63 63 70 / 0.5);
	}

	.group-section:last-child {
		border-bottom: none;
	}

	.group-header {
		display: flex;
		cursor: pointer;
		align-items: center;
		gap: 0.375rem;
		padding: 0.5rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: rgb(161 161 170);
		transition: all 0.15s;
	}

	.group-header:hover {
		background-color: rgb(39 39 42 / 0.5);
		color: rgb(212 212 216);
	}

	.chevron {
		display: inline-block;
		font-size: 0.6rem;
		color: rgb(113 113 122);
		transition: transform 0.15s ease;
	}

	details[open] > .group-header .chevron {
		transform: rotate(90deg);
	}

	.swatch {
		height: 1.25rem;
		border-radius: 0.125rem;
		border: 1px solid rgb(82 82 91 / 0.5);
		transition: all 0.15s;
		cursor: pointer;
	}

	.swatch:hover {
		transform: scale(1.05);
		border-color: rgb(113 113 122);
	}

	.swatch.selected {
		border-color: rgb(212 212 216);
		box-shadow: 0 0 0 1px rgb(161 161 170);
	}
</style>
