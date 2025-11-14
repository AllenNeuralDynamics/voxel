<script lang="ts">
	import { COLORMAP_COLORS, isValidHex } from '$lib/widgets/preview/colormap';

	interface Props {
		color: string;
		onColorChange: (color: string) => void;
	}

	let { color = $bindable('#ffffff'), onColorChange }: Props = $props();

	let isOpen = $state(false);
	let customColorInput = $state(color);

	// Get preset colors from the colormap
	const presetColors = Object.values(COLORMAP_COLORS);

	function handlePresetClick(hexColor: string) {
		color = hexColor;
		customColorInput = hexColor;
		onColorChange(hexColor);
		isOpen = false;
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

	function togglePicker() {
		isOpen = !isOpen;
	}

	function handleClickOutside(e: MouseEvent) {
		const target = e.target as HTMLElement;
		if (!target.closest('.color-picker-container')) {
			isOpen = false;
		}
	}

	$effect(() => {
		if (isOpen) {
			document.addEventListener('click', handleClickOutside);
		} else {
			document.removeEventListener('click', handleClickOutside);
		}

		return () => {
			document.removeEventListener('click', handleClickOutside);
		};
	});
</script>

<div class="color-picker-container relative">
	<!-- Color indicator button -->
	<button
		type="button"
		onclick={togglePicker}
		class="h-4 w-4 rounded border border-zinc-600 transition-all hover:scale-110 hover:border-zinc-400"
		style="background-color: {color}"
		aria-label="Pick color"
	></button>

	<!-- Popover -->
	{#if isOpen}
		<div
			role="dialog"
			aria-label="Color picker"
			tabindex="-1"
			class="absolute top-6 left-0 z-50 rounded-md border border-zinc-700 bg-zinc-900 p-2 shadow-xl"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => {
				if (e.key === 'Escape') {
					isOpen = false;
				}
			}}
		>
			<!-- Preset colors -->
			<div class="mb-2">
				<div class="mb-1.5 text-[0.65rem] font-medium text-zinc-400">Presets</div>
				<div class="grid grid-cols-4 gap-1.5">
					{#each presetColors as presetColor (presetColor)}
						<button
							type="button"
							onclick={() => handlePresetClick(presetColor)}
							class="h-6 w-6 rounded border transition-all hover:scale-110 {color.toLowerCase() ===
							presetColor.toLowerCase()
								? 'border-zinc-300 ring-1 ring-zinc-400'
								: 'border-zinc-600 hover:border-zinc-400'}"
							style="background-color: {presetColor}"
							aria-label="Select preset color"
						></button>
					{/each}
				</div>
			</div>

			<!-- Custom color -->
			<div class="border-t border-zinc-700 pt-2">
				<div class="mb-1.5 text-[0.65rem] font-medium text-zinc-400">Custom</div>
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
		</div>
	{/if}
</div>

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
