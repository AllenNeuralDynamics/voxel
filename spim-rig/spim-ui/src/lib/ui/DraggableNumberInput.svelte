<script lang="ts">
	interface Props {
		value?: number;
		min?: number;
		max?: number;
		step?: number;
		decimals?: number; // Number of decimal places to display
		placeholder?: string;
		numCharacters?: number; // Number of characters wide
		color?: string; // Text color
		align?: 'left' | 'right';
		onChange?: (newValue: number) => void; // Optional callback for value changes
	}

	let {
		value = $bindable(0),
		min = -Infinity,
		max = Infinity,
		step = 1,
		decimals,
		placeholder = '',
		numCharacters = 4,
		color = 'inherit',
		align = 'left',
		onChange: onValueChange
	}: Props = $props();

	// Compute display value with proper decimal formatting
	let displayValue = $derived(() => {
		if (decimals !== undefined) {
			return value.toFixed(decimals);
		}
		return value.toString();
	});

	let isDragging = $state(false);
	let isPotentialDrag = $state(false);
	let dragStartX = $state(0);
	let dragStartValue = $state(0);
	const DRAG_THRESHOLD = 3; // pixels to move before starting drag

	function handleMouseDown(e: MouseEvent) {
		// Only start drag on left click
		if (e.button !== 0) return;

		isPotentialDrag = true;
		dragStartX = e.clientX;
		dragStartValue = value;

		// Add global listeners
		document.addEventListener('mousemove', handleMouseMove);
		document.addEventListener('mouseup', handleMouseUp);
	}

	function handleMouseMove(e: MouseEvent) {
		if (!isPotentialDrag && !isDragging) return;

		// Calculate delta in pixels
		const deltaX = e.clientX - dragStartX;

		// Check if we've moved past the threshold to start dragging
		if (!isDragging && Math.abs(deltaX) > DRAG_THRESHOLD) {
			isDragging = true;
			e.preventDefault();
		}

		if (!isDragging) return;

		// Convert to value change (1 pixel = 1 step by default, adjust sensitivity if needed)
		const sensitivity = 1; // pixels per step
		const deltaValue = Math.round(deltaX / sensitivity) * step;

		// Calculate new value
		let newValue = dragStartValue + deltaValue;

		// Clamp to min/max
		newValue = Math.max(min, Math.min(max, newValue));

		// Update value
		value = newValue;

		// Call callback if provided
		if (onValueChange) {
			onValueChange(newValue);
		}
	}

	function handleMouseUp() {
		isDragging = false;
		isPotentialDrag = false;
		document.removeEventListener('mousemove', handleMouseMove);
		document.removeEventListener('mouseup', handleMouseUp);
	}

	function handleInput(e: Event) {
		const target = e.target as HTMLInputElement;
		let newValue = parseFloat(target.value);

		if (isNaN(newValue)) return;

		// Clamp to min/max
		newValue = Math.max(min, Math.min(max, newValue));

		value = newValue;

		// Call callback if provided
		if (onValueChange) {
			onValueChange(newValue);
		}
	}

	function handleWheel(e: WheelEvent) {
		e.preventDefault();

		// Scroll up (negative deltaY) increases value, scroll down decreases
		const direction = e.deltaY < 0 ? 1 : -1;
		let newValue = value + direction * step;

		// Clamp to min/max
		newValue = Math.max(min, Math.min(max, newValue));

		value = newValue;

		// Call callback if provided
		if (onValueChange) {
			onValueChange(newValue);
		}
	}

	// Cleanup on destroy
	$effect(() => {
		return () => {
			document.removeEventListener('mousemove', handleMouseMove);
			document.removeEventListener('mouseup', handleMouseUp);
		};
	});
</script>

<input
	type="text"
	{placeholder}
	value={displayValue()}
	oninput={handleInput}
	onmousedown={handleMouseDown}
	onwheel={handleWheel}
	style:width="{numCharacters + 1}ch"
	style:color
	style:text-align={align}
	style:cursor="ew-resize"
	class="draggable-input"
/>

<style>
	.draggable-input {
		user-select: none;
		border: 1px solid transparent;
		background: transparent;
		padding: 0.125rem 0.05rem;
		font-family: monospace;
		font-size: 0.65rem;
		transition: all 0.15s;
	}

	.draggable-input:hover {
		border-color: rgb(82 82 91);
		background: rgb(24 24 27);
		color: rgb(212 212 216);
	}

	.draggable-input:focus {
		border-color: rgb(113 113 122);
		background: rgb(24 24 27);
		outline: none;
	}

	.draggable-input::-webkit-inner-spin-button,
	.draggable-input::-webkit-outer-spin-button {
		-webkit-appearance: none;
		margin: 0;
	}
</style>
