<script lang="ts">
	type Size = 'xs' | 'sm' | 'md' | 'lg';

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
		prefix?: string;
		suffix?: string;
		snapValue?: number | (() => number);
		size?: Size;
		class?: string;
		throttle?: number;
		debounce?: number;
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
		prefix,
		suffix,
		snapValue,
		size = 'md',
		class: className = '',
		throttle = 100,
		debounce = 400,
		onChange: onValueChange
	}: Props = $props();

	let lastDragCallTime = 0;
	let dragThrottleTimer: ReturnType<typeof setTimeout> | undefined;

	function throttledCallback(newValue: number) {
		if (!onValueChange) return;
		if (throttle <= 0) {
			onValueChange(newValue);
			return;
		}
		const now = Date.now();
		if (now - lastDragCallTime >= throttle) {
			lastDragCallTime = now;
			onValueChange(newValue);
		} else {
			clearTimeout(dragThrottleTimer);
			dragThrottleTimer = setTimeout(() => {
				lastDragCallTime = Date.now();
				onValueChange(newValue);
			}, throttle - (now - lastDragCallTime));
		}
	}

	// --- Debounce state ---
	let isEditing = $state(false);
	let editingText = $state('');
	let debounceTimer: ReturnType<typeof setTimeout> | undefined;

	function commitEdit() {
		clearTimeout(debounceTimer);
		if (!isEditing) return;
		isEditing = false;

		const parsed = parseFloat(editingText);
		if (isNaN(parsed)) return; // discard invalid input

		const clamped = Math.max(min, Math.min(max, parsed));
		value = clamped;
		if (onValueChange) {
			onValueChange(clamped);
		}
	}

	let inputValue = $derived(() => {
		if (isEditing) return editingText;
		if (decimals !== undefined) return value.toFixed(decimals);
		return value.toString();
	});

	const sizeClasses: Record<Size, { wrapper: string; input: string; stack: string }> = {
		xs: {
			wrapper: 'h-4 rounded-[2px]',
			input: 'text-[0.6rem] px-0 py-0',
			stack: 'w-4'
		},
		sm: {
			wrapper: 'h-5 rounded',
			input: 'text-[0.65rem] px-0.5 py-0.5',
			stack: 'w-4'
		},
		md: {
			wrapper: 'h-7 rounded',
			input: 'text-xs px-0.5 py-0.5',
			stack: 'w-5'
		},
		lg: {
			wrapper: 'h-8 rounded',
			input: 'text-sm px-0.5 py-0.5',
			stack: 'w-5'
		}
	};

	let inputElement = $state<HTMLInputElement | undefined>();
	let wrapperElement = $state<HTMLDivElement | undefined>();


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
			document.body.style.cursor = 'ew-resize';
			e.preventDefault();
		}

		if (!isDragging) return;

		const sensitivity = 1;
		const deltaValue = Math.round(deltaX / sensitivity) * step;
		let newValue = dragStartValue + deltaValue;
		newValue = Math.max(min, Math.min(max, newValue));
		value = newValue;

		throttledCallback(newValue);
	}

	function handleMouseUp() {
		clearTimeout(dragThrottleTimer);
		if (isDragging && onValueChange) {
			onValueChange(value);
		}
		isDragging = false;
		isPotentialDrag = false;
		document.body.style.cursor = '';
		document.removeEventListener('mousemove', handleMouseMove);
		document.removeEventListener('mouseup', handleMouseUp);
	}

	function handleDoubleClick() {
		if (snapValue === undefined) return;
		const resolved = typeof snapValue === 'function' ? snapValue() : snapValue;
		value = resolved;
		if (onValueChange) {
			onValueChange(resolved);
		}
	}

	function handleInput(e: Event) {
		const target = e.target as HTMLInputElement;

		if (debounce > 0) {
			isEditing = true;
			editingText = target.value;
			clearTimeout(debounceTimer);
			debounceTimer = setTimeout(commitEdit, debounce);
			return;
		}

		let newValue = parseFloat(target.value);
		if (isNaN(newValue)) return;

		newValue = Math.max(min, Math.min(max, newValue));
		value = newValue;

		if (onValueChange) {
			onValueChange(newValue);
		}
	}

	function handleBlur() {
		if (debounce > 0) commitEdit();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && debounce > 0) {
			commitEdit();
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
			clearTimeout(debounceTimer);
			document.removeEventListener('mousemove', handleMouseMove);
			document.removeEventListener('mouseup', handleMouseUp);
		};
	});

	$effect(() => {
		if (!wrapperElement) return;

		wrapperElement.addEventListener('wheel', handleWheel, { passive: false });

		return () => {
			if (wrapperElement) {
				wrapperElement.removeEventListener('wheel', handleWheel);
			}
		};
	});
</script>

{#if showButtons}
	<div
		bind:this={wrapperElement}
		class="flex items-stretch border border-input bg-transparent transition-colors focus-within:border-ring {sizeClasses[
			size
		].wrapper} {className}"
	>
		{#if prefix}
			<span
				role="button"
				tabindex="-1"
				onmousedown={draggable ? handleMouseDown : undefined}
				ondblclick={snapValue !== undefined ? handleDoubleClick : undefined}
				class="flex shrink-0 items-center ps-1.5 pe-1 font-mono whitespace-nowrap text-muted-foreground select-none {sizeClasses[
					size
				].input}"
				class:cursor-ew-resize={draggable}>{prefix}</span
			>
		{/if}
		<input
			bind:this={inputElement}
			type="text"
			{placeholder}
			value={inputValue()}
			oninput={handleInput}
			onblur={handleBlur}
			onkeydown={handleKeydown}
			style:width="{numCharacters + 1}ch"
			style:color
			style:text-align={align}
			class="flex-1 border-none bg-transparent ps-1.5 pe-1 font-mono text-foreground outline-none {sizeClasses[size]
				.input}"
		/>
		{#if suffix}
			<span
				class="pointer-events-none flex items-center pe-1.5 font-mono text-muted-foreground {sizeClasses[size].input}"
				>{suffix}</span
			>
		{/if}
		<div class="flex cursor-pointer flex-col border-l border-input {sizeClasses[size].stack}">
			<button
				class="flex flex-1 items-center justify-center rounded-tr border-b border-input bg-transparent text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
				onclick={increment}
				disabled={value >= max}
				aria-label="Increment"
			>
				<svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor"><path d="M4 0L8 5H0L4 0Z" /></svg>
			</button>
			<button
				class="flex flex-1 items-center justify-center rounded-br bg-transparent text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
				onclick={decrement}
				disabled={value <= min}
				aria-label="Decrement"
			>
				<svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor"><path d="M4 5L0 0H8L4 5Z" /></svg>
			</button>
		</div>
	</div>
{:else}
	<div
		bind:this={wrapperElement}
		class="inline-flex items-stretch border border-transparent bg-transparent transition-colors focus-within:border-ring {sizeClasses[
			size
		].wrapper} {className}"
	>
		{#if prefix}
			<span
				role="button"
				tabindex="-1"
				onmousedown={draggable ? handleMouseDown : undefined}
				ondblclick={snapValue !== undefined ? handleDoubleClick : undefined}
				class="flex shrink-0 items-center ps-1 pe-0.5 font-mono whitespace-nowrap text-muted-foreground select-none {sizeClasses[
					size
				].input}"
				class:cursor-ew-resize={draggable}>{prefix}</span
			>
		{/if}
		<input
			bind:this={inputElement}
			type="text"
			{placeholder}
			value={inputValue()}
			oninput={handleInput}
			onblur={handleBlur}
			onkeydown={handleKeydown}
			style:width="{numCharacters + 1}ch"
			style:color
			style:text-align={align}
			class="border-none bg-transparent font-mono text-foreground outline-none {sizeClasses[size].input}"
		/>
		{#if suffix}
			<span class="pointer-events-none flex items-center font-mono text-muted-foreground {sizeClasses[size].input}"
				>{suffix}</span
			>
		{/if}
	</div>
{/if}

<style>
	/* Hide native spin buttons */
	input::-webkit-inner-spin-button,
	input::-webkit-outer-spin-button {
		-webkit-appearance: none;
		margin: 0;
	}

	input {
		user-select: none;
	}
</style>
