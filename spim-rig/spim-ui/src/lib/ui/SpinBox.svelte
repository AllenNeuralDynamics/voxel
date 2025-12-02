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
		showButtons?: boolean; // Show increment/decrement buttons
		draggable?: boolean; // Enable drag to change value
		classNames?: string; // Additional classes for input-wrapper
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
		showButtons = true,
		draggable = true,
		classNames = '',
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
		// Only start drag on left click and if draggable is enabled
		if (e.button !== 0 || !draggable) return;

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

	function increment() {
		let newValue = value + step;
		newValue = Math.max(min, Math.min(max, newValue));
		value = newValue;
		if (onValueChange) {
			onValueChange(newValue);
		}
	}

	function decrement() {
		let newValue = value - step;
		newValue = Math.max(min, Math.min(max, newValue));
		value = newValue;
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

<div class="input-wrapper {classNames}" class:with-buttons={showButtons}>
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
		class:draggable
	/>
	{#if showButtons}
		<div class="button-stack">
			<button class="spin-button spin-up" onclick={increment} disabled={value >= max} aria-label="Increment">
				<svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor">
					<path d="M4 0L8 5H0L4 0Z" />
				</svg>
			</button>
			<button class="spin-button spin-down" onclick={decrement} disabled={value <= min} aria-label="Decrement">
				<svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor">
					<path d="M4 5L0 0H8L4 5Z" />
				</svg>
			</button>
		</div>
	{/if}
</div>

<style>
	.input-wrapper {
		--border-width: 1px;
		--border-color: rgb(63 63 70);
		--border-color-hover: rgb(82 82 91);

		display: inline-flex;
		align-items: stretch;
		transition: all 0.15s;
	}

	.input-wrapper.with-buttons {
		display: flex;
		width: 100%;
		border: var(--border-width) solid var(--border-color);
		border-radius: 2px;
		background: rgb(24 24 27);

		&:hover {
			border-color: var(--border-color-hover);
		}
	}

	.input-wrapper.with-buttons input {
		flex: 1;
		border: none;
		background: transparent;
		padding-inline-start: 0.2rem;
		margin-inline-end: 0.2rem;
	}

	.input-wrapper.with-buttons input.draggable {
		cursor: ew-resize;
	}

	.input-wrapper.with-buttons input:hover,
	.input-wrapper.with-buttons input:focus {
		border: none;
		background: transparent;
	}

	input {
		user-select: none;
		border: 1px solid transparent;
		background: transparent;
		padding: 0.125rem 0.05rem;
		font-family: monospace;
		font-size: 0.65rem;
		transition: all 0.15s;
	}

	input.draggable {
		cursor: ew-resize;
	}

	input:hover {
		border-color: rgb(82 82 91);
		background: rgb(24 24 27);
		color: rgb(212 212 216);
	}

	input:focus {
		border-color: rgb(113 113 122);
		background: rgb(24 24 27);
		outline: none;
	}

	input::-webkit-inner-spin-button,
	input::-webkit-outer-spin-button {
		-webkit-appearance: none;
		margin: 0;
	}

	.button-stack {
		display: flex;
		flex-direction: column;
		align-self: stretch;
		width: 1.25rem;
		cursor: pointer;
	}

	.input-wrapper.with-buttons:hover .button-stack {
		border-color: var(--border-color-hover);
	}

	.spin-button {
		z-index: 999;
		display: flex;
		align-items: center;
		justify-content: center;
		flex: 1;
		padding: 0;
		margin: 0;
		border: none;
		background: transparent;
		color: rgb(113 113 122);
		margin-right: calc(-1 * var(--border-width));
		border: var(--border-width) solid var(--border-color);

		transition: all 0.1s;

		& svg {
			pointer-events: none;
		}

		&:disabled {
			color: rgb(63 63 70);
			cursor: not-allowed;
			opacity: 0.4;
		}

		&:not(disabled) {
			&:active,
			&:hover {
				color: rgb(212 212 216);
				background: rgb(39 39 42);
			}
		}
	}

	.spin-up {
		margin-top: calc(-1 * var(--border-width));
		border-top-right-radius: 2px;
		border-bottom: none;
	}
	.spin-down {
		border-bottom-right-radius: 2px;
		margin-bottom: calc(-1 * var(--border-width));
		border-top: none;
	}
</style>
