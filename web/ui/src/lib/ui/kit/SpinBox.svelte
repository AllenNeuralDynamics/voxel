<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const spinBoxVariants = tv({
		slots: {
			wrapper: ['items-center', 'transition-colors focus-within:border-focused'],
			input: ['m-0 border-none bg-transparent py-0 font-mono text-fg outline-none'],
			stack: ['flex cursor-pointer self-stretch flex-col border-l border-input'],
			stepButton: [
				'flex flex-1 items-center justify-center',
				'bg-transparent text-fg-faint',
				'transition-colors hover:bg-element-hover hover:text-fg',
				'disabled:cursor-not-allowed disabled:opacity-40'
			],
			prefix: ['shrink-0 font-mono whitespace-nowrap', 'text-fg-muted select-none'],
			suffix: ['pointer-events-none font-mono text-fg-muted']
		},
		variants: {
			variant: {
				ghost: {
					wrapper: 'bg-transparent hover:border-fg/20'
				},
				filled: {
					wrapper: 'bg-element-bg hover:bg-element-hover'
				}
			},
			size: {
				xs: {
					wrapper: 'h-ui-xs rounded',
					input: 'text-xs leading-none px-0.5',
					prefix: 'text-xs leading-none',
					suffix: 'text-xs leading-none',
					stack: 'w-4'
				},
				sm: {
					wrapper: 'h-ui-sm rounded',
					input: 'text-xs leading-none px-0.5',
					prefix: 'text-xs leading-none',
					suffix: 'text-xs leading-none',
					stack: 'w-4'
				},
				md: {
					wrapper: 'h-ui-md rounded',
					input: 'text-sm leading-none px-0.5',
					prefix: 'text-sm leading-none',
					suffix: 'text-sm leading-none',
					stack: 'w-5'
				},
				lg: {
					wrapper: 'h-ui-lg rounded',
					input: 'text-base leading-none px-0.5',
					prefix: 'text-base leading-none',
					suffix: 'text-base leading-none',
					stack: 'w-5'
				}
			},
			appearance: {
				full: {
					wrapper: 'flex border border-input',
					input: 'flex-1 ps-1.5 pe-1',
					prefix: 'ps-1.5 pe-1',
					suffix: 'pe-1.5'
				},
				bordered: {
					wrapper: 'flex border border-input',
					input: 'flex-1 ps-1.5 pe-1',
					prefix: 'ps-1.5 pe-1',
					suffix: 'pe-1.5',
					stack: 'hidden'
				},
				inline: {
					wrapper: 'inline-flex border border-transparent',
					prefix: 'ps-1 pe-0.5',
					stack: 'hidden'
				}
			}
		},
		defaultVariants: {
			variant: 'filled',
			size: 'md',
			appearance: 'full'
		}
	});

	export type SpinBoxVariants = VariantProps<typeof spinBoxVariants>;
</script>

<script lang="ts">
	import { cn } from '$lib/utils';
	import { useEventListener, useThrottle, useDebounce } from 'runed';

	interface Props extends SpinBoxVariants {
		value?: number;
		min?: number;
		max?: number;
		step?: number;
		decimals?: number;
		placeholder?: string;
		numCharacters?: number;
		color?: string;
		align?: 'left' | 'right';
		draggable?: boolean;
		prefix?: string;
		suffix?: string;
		snapValue?: number | (() => number);
		disabled?: boolean;
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
		variant = 'filled',
		appearance = 'full',
		draggable = true,
		prefix,
		suffix,
		snapValue,
		disabled = false,
		size = 'md',
		class: className = '',
		throttle = 100,
		debounce = 400,
		onChange: onValueChange
	}: Props = $props();

	const styles = $derived(spinBoxVariants({ variant, size, appearance }));

	const throttledDragCallback = useThrottle(
		(newValue: number) => {
			onValueChange?.(newValue);
		},
		() => throttle
	);

	let isEditing = $state(false);
	let editingText = $state('');
	const debouncedCommit = useDebounce(
		() => commitEdit(),
		() => debounce
	);

	function snapToStep(v: number): number {
		if (step <= 0 || !isFinite(step)) return v;
		if (!isFinite(min)) return Math.round(v / step) * step;
		return min + Math.round((v - min) / step) * step;
	}

	function commitEdit() {
		if (!isEditing) return;
		isEditing = false;

		const parsed = parseFloat(editingText);
		if (isNaN(parsed)) return; // discard invalid input

		const snapped = snapToStep(Math.max(min, Math.min(max, parsed)));
		const clamped = Math.max(min, Math.min(max, snapped));
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

		throttledDragCallback(newValue);
	}

	function handleMouseUp() {
		throttledDragCallback.cancel();
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
			debouncedCommit();
			return;
		}

		let newValue = parseFloat(target.value);
		if (isNaN(newValue)) return;

		newValue = Math.max(min, Math.min(max, snapToStep(newValue)));
		value = newValue;

		if (onValueChange) {
			onValueChange(newValue);
		}
	}

	function handleBlur() {
		if (debounce > 0) {
			debouncedCommit.cancel();
			commitEdit();
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && debounce > 0) {
			debouncedCommit.cancel();
			commitEdit();
		}
	}

	function handleWheel(e: WheelEvent) {
		if (!e.ctrlKey) return;
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

	useEventListener(() => wrapperElement, 'wheel', handleWheel, { passive: false });

	// Safety net: clean up drag listeners if component unmounts mid-drag
	$effect(() => {
		return () => {
			document.removeEventListener('mousemove', handleMouseMove);
			document.removeEventListener('mouseup', handleMouseUp);
		};
	});
</script>

<div
	bind:this={wrapperElement}
	class={cn(styles.wrapper({ class: className }), disabled && 'pointer-events-none border-input/50')}
>
	{#if prefix}
		<span
			role="button"
			tabindex="-1"
			onmousedown={draggable ? handleMouseDown : undefined}
			ondblclick={snapValue !== undefined ? handleDoubleClick : undefined}
			class={cn(styles.prefix(), draggable && 'cursor-ew-resize')}>{prefix}</span
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
		class={styles.input()}
	/>
	{#if suffix}
		<span class={styles.suffix()}>{suffix}</span>
	{/if}
	<div class={styles.stack()}>
		<button
			class={cn(styles.stepButton(), 'rounded-tr border-b border-input')}
			onclick={increment}
			disabled={value >= max}
			aria-label="Increment"
		>
			<svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor"><path d="M4 0L8 5H0L4 0Z" /></svg>
		</button>
		<button
			class={cn(styles.stepButton(), 'rounded-br')}
			onclick={decrement}
			disabled={value <= min}
			aria-label="Decrement"
		>
			<svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor"><path d="M4 5L0 0H8L4 5Z" /></svg>
		</button>
	</div>
</div>

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
