<script lang="ts">
	type Size = 'sm' | 'md' | 'lg';

	interface Props {
		value?: number;
		min?: number;
		max?: number;
		step?: number;
		decimals?: number;
		placeholder?: string;
		numCharacters?: number;
		color?: string;
		align?: 'left' | 'right';
		showButtons?: boolean;
		draggable?: boolean;
		classNames?: string;
		size?: Size;
		onChange?: (newValue: number) => void;
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
		size = 'md',
		onChange: onValueChange
	}: Props = $props();

	const sizeMap: Record<Size, { height: string; fontSize: string }> = {
		sm: { height: '1.5rem', fontSize: '0.65rem' },
		md: { height: '1.75rem', fontSize: '0.75rem' },
		lg: { height: '2rem', fontSize: '0.875rem' }
	};

	let inputElement: HTMLInputElement | undefined;

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
	const DRAG_THRESHOLD = 3;

	function handleMouseDown(e: MouseEvent) {
		if (e.button !== 0 || !draggable) return;

		isPotentialDrag = true;
		dragStartX = e.clientX;
		dragStartValue = value;

		document.addEventListener('mousemove', handleMouseMove);
		document.addEventListener('mouseup', handleMouseUp);
	}

	function handleMouseMove(e: MouseEvent) {
		if (!isPotentialDrag && !isDragging) return;

		const deltaX = e.clientX - dragStartX;

		if (!isDragging && Math.abs(deltaX) > DRAG_THRESHOLD) {
			isDragging = true;
			e.preventDefault();
		}

		if (!isDragging) return;

		const sensitivity = 1;
		const deltaValue = Math.round(deltaX / sensitivity) * step;
		let newValue = dragStartValue + deltaValue;
		newValue = Math.max(min, Math.min(max, newValue));
		value = newValue;

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

		newValue = Math.max(min, Math.min(max, newValue));
		value = newValue;

		if (onValueChange) {
			onValueChange(newValue);
		}
	}

	function handleWheel(e: WheelEvent) {
		e.preventDefault();

		const direction = e.deltaY < 0 ? 1 : -1;
		let newValue = value + direction * step;
		newValue = Math.max(min, Math.min(max, newValue));
		value = newValue;

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

	$effect(() => {
		return () => {
			document.removeEventListener('mousemove', handleMouseMove);
			document.removeEventListener('mouseup', handleMouseUp);
		};
	});

	$effect(() => {
		if (!inputElement) return;

		inputElement.addEventListener('wheel', handleWheel, { passive: false });

		return () => {
			if (inputElement) {
				inputElement.removeEventListener('wheel', handleWheel);
			}
		};
	});
</script>

<div
	class="input-wrapper {classNames}"
	class:with-buttons={showButtons}
	style:--spinbox-height={sizeMap[size].height}
	style:--spinbox-font-size={sizeMap[size].fontSize}
>
	<input
		bind:this={inputElement}
		type="text"
		{placeholder}
		value={displayValue()}
		oninput={handleInput}
		onmousedown={handleMouseDown}
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

		display: inline-flex;
		align-items: stretch;
		height: var(--spinbox-height, 1.75rem);
		transition: all 0.15s;
	}

	.input-wrapper.with-buttons {
		display: flex;
		width: 100%;
		border: var(--border-width) solid var(--input);
		border-radius: 2px;
		background: transparent;

		&:hover {
			border-color: color-mix(in oklch, var(--foreground) 20%, transparent);
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
		font-size: var(--spinbox-font-size, 0.75rem);
		color: var(--foreground);
		transition: all 0.15s;
	}

	input.draggable {
		cursor: ew-resize;
	}

	input:hover {
		border-color: color-mix(in oklch, var(--foreground) 20%, transparent);
	}

	input:focus {
		border-color: var(--ring);
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
		width: 1.25rem;
		cursor: pointer;
	}

	.spin-button {
		display: flex;
		align-items: center;
		justify-content: center;
		flex: 1;
		padding: 0;
		margin: 0;
		border: none;
		background: transparent;
		color: var(--input);
		border-left: var(--border-width) solid var(--input);

		transition: all 0.1s;

		& svg {
			pointer-events: none;
		}

		&:disabled {
			cursor: not-allowed;
			opacity: 0.4;
		}

		&:not(disabled) {
			&:active,
			&:hover {
				color: var(--muted-foreground);
				background: var(--accent);
			}
		}
	}

	.spin-up {
		border-top-right-radius: 2px;
	}
	.spin-down {
		border-bottom-right-radius: 2px;
		border-top: var(--border-width) solid var(--input);
	}
</style>
