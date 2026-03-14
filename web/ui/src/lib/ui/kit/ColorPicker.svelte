<script lang="ts">
	import { Popover } from 'bits-ui';
	import { isValidHex } from '$lib/utils';
	import type { PopoverContentProps } from 'bits-ui';

	interface Props {
		color: string;
		presetColors?: string[];
		onColorChange: (color: string) => void;
		align?: PopoverContentProps['align'];
	}

	let { color = $bindable('#ffffff'), presetColors = [], onColorChange, align = 'start' }: Props = $props();

	let customColorInput = $state(color);

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
		class="hover:border-fg-muted h-2.5 w-2.5 rounded-full border border-border transition-all"
		style="background-color: {color}"
		aria-label="Pick color"
	/>

	<Popover.Content
		class="bg-floating z-50 rounded-md border border-border p-2 shadow-xl outline-none"
		sideOffset={4}
		{align}
	>
		{#if presetColors.length > 0}
			<!-- Preset colors -->
			<div class="mb-2">
				<div class="grid grid-cols-4 gap-1.5">
					{#each presetColors as presetColor (presetColor)}
						<button
							type="button"
							onclick={() => handlePresetClick(presetColor)}
							class="h-5 w-5 rounded-full border transition-all hover:scale-110 {color.toLowerCase() ===
							presetColor.toLowerCase()
								? 'border-focused ring-focused ring-1'
								: 'hover:border-fg-muted border-border'}"
							style="background-color: {presetColor}"
							aria-label="Select preset color"
						></button>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Custom color -->
		<div class={presetColors.length > 0 ? 'border-t border-border pt-2' : ''}>
			<div class="flex gap-1.5">
				<!-- Native color picker -->
				<input
					type="color"
					value={color}
					oninput={handleCustomColorChange}
					class="bg-element-bg h-6 w-8 cursor-pointer rounded border border-input"
				/>
				<!-- Hex input -->
				<input
					type="text"
					value={customColorInput}
					oninput={handleCustomInputChange}
					onblur={handleCustomInputBlur}
					placeholder="#ff00ff"
					size="7"
					class="bg-element-bg text-fg placeholder-fg-muted focus:border-focused h-6 min-w-0 rounded border border-input px-1.5 font-mono text-[0.65rem] focus:outline-none"
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
