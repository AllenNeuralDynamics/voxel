<script lang="ts">
	import { Popover } from 'bits-ui';
	import { COLORMAP_COLORS, isValidHex } from '$lib/widgets/preview/colormap';
	import type { PopoverContentProps } from 'bits-ui';

	interface Props {
		color: string;
		onColorChange: (color: string) => void;
		align?: PopoverContentProps['align'];
	}

	let { color = $bindable('#ffffff'), onColorChange, align = 'start' }: Props = $props();

	let customColorInput = $state(color);

	// Get preset colors from the colormap
	const presetColors = Object.values(COLORMAP_COLORS);

	function handlePresetClick(hexColor: string) {
		color = hexColor;
		customColorInput = hexColor;
		onColorChange(hexColor);
	}

	function handleCustomColorChange(e: Event) {
		const input = e.target as HTMLInputElement;
		const newColor = input.value;
		if (isValidHex(newColor)) {
			color = newColor;
			customColorInput = newColor;
			onColorChange(newColor);
		}
	}

	function handleCustomInputChange(e: Event) {
		const input = e.target as HTMLInputElement;
		customColorInput = input.value;
	}

	function handleCustomInputBlur() {
		if (isValidHex(customColorInput)) {
			color = customColorInput;
			onColorChange(customColorInput);
		} else {
			// Reset to current valid color if invalid
			customColorInput = color;
		}
	}
</script>

<Popover.Root>
	<Popover.Trigger
		class="h-2.5 w-2.5 rounded-full border border-zinc-600/50 transition-all hover:scale-110 hover:border-zinc-500"
		style="background-color: {color}"
		aria-label="Pick color"
	/>

	<Popover.Content
		class="z-50 rounded-md border border-zinc-700 bg-zinc-900 p-2 shadow-xl outline-none"
		sideOffset={4}
		{align}
	>
		<!-- Preset colors -->
		<div class="mb-2">
			<div class="grid grid-cols-4 gap-1.5">
				{#each presetColors as presetColor (presetColor)}
					<button
						type="button"
						onclick={() => handlePresetClick(presetColor)}
						class="h-5 w-5 rounded-full border transition-all hover:scale-110 {color.toLowerCase() ===
						presetColor.toLowerCase()
							? 'border-zinc-300 ring-1 ring-zinc-400'
							: 'border-zinc-600/50 hover:border-zinc-500'}"
						style="background-color: {presetColor}"
						aria-label="Select preset color"
					></button>
				{/each}
			</div>
		</div>

		<!-- Custom color -->
		<div class="border-t border-zinc-700 pt-2">
			<div class="flex gap-1.5">
				<!-- Native color picker -->
				<input
					type="color"
					value={color}
					oninput={handleCustomColorChange}
					class="h-6 w-8 cursor-pointer rounded border border-zinc-600 bg-zinc-800"
				/>
				<!-- Hex input -->
				<input
					type="text"
					value={customColorInput}
					oninput={handleCustomInputChange}
					onblur={handleCustomInputBlur}
					placeholder="#ff00ff"
					class="h-6 flex-1 rounded border border-zinc-600 bg-zinc-800 px-1.5 font-mono text-[0.65rem] text-zinc-200 placeholder-zinc-500 focus:border-zinc-400 focus:outline-none"
				/>
			</div>
		</div>
	</Popover.Content>
</Popover.Root>

<style>
	/* Customize native color input */
	input[type='color'] {
		-webkit-appearance: none;
		-moz-appearance: none;
		appearance: none;
		padding: 0;
		cursor: pointer;
	}

	input[type='color']::-webkit-color-swatch-wrapper {
		padding: 2px;
	}

	input[type='color']::-webkit-color-swatch {
		border: none;
		border-radius: 4px;
	}

	input[type='color']::-moz-color-swatch {
		border: none;
		border-radius: 4px;
	}
</style>
