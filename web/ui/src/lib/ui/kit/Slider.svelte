<script lang="ts">
	interface Props {
		value?: number;
		target: number;
		min?: number;
		max?: number;
		step?: number;
		throttle?: number;
		onChange?: (value: number) => void;
		class?: string;
	}

	let { value, target, min = 0, max = 100, step = 1, throttle = 0, onChange, class: className = '' }: Props = $props();

	const fillPercentage = $derived(
		value != null ? ((value - min) / (max - min)) * 100 : ((target - min) / (max - min)) * 100
	);

	let inputElement = $state<HTMLInputElement | undefined>();
	let lastInputTime = 0;
	let throttleTimer: ReturnType<typeof setTimeout> | undefined;

	function handleInput(e: Event) {
		if (throttle <= 0 || !onChange) return;
		const v = parseFloat((e.currentTarget as HTMLInputElement).value);
		const now = Date.now();
		if (now - lastInputTime >= throttle) {
			lastInputTime = now;
			onChange(v);
		} else {
			clearTimeout(throttleTimer);
			throttleTimer = setTimeout(
				() => {
					lastInputTime = Date.now();
					onChange(v);
				},
				throttle - (now - lastInputTime)
			);
		}
	}

	let isFocused = $state(false);

	function handleWheel(e: WheelEvent) {
		if (!isFocused || !e.ctrlKey) return;
		e.preventDefault();
		const direction = e.deltaY < 0 ? 1 : -1;
		const newValue = Math.max(min, Math.min(max, target + direction * step));
		onChange?.(newValue);
	}

	$effect(() => {
		if (!inputElement) return;
		inputElement.addEventListener('wheel', handleWheel, { passive: false });
		return () => inputElement?.removeEventListener('wheel', handleWheel);
	});
</script>

<input
	bind:this={inputElement}
	type="range"
	onfocus={() => (isFocused = true)}
	onblur={() => (isFocused = false)}
	{min}
	{max}
	{step}
	value={target}
	oninput={throttle > 0 ? handleInput : undefined}
	onchange={(e) => {
		clearTimeout(throttleTimer);
		onChange?.(parseFloat(e.currentTarget.value));
	}}
	class="slider {className}"
	style="--fill-percentage: {fillPercentage}%"
/>

<style>
	.slider {
		width: 100%;
		appearance: none;
		outline: none;
		cursor: pointer;
		background: transparent;
		--thumb-width: 0.2rem;
		--thumb-height: 0.75rem;
		--thumb-radius: 2px;
		--thumb-color: var(--color-muted-foreground);
		--track-filled: var(--color-muted-foreground);
		--track-unfilled: transparent;
		--track-height: 0.5rem;
		--track-radius: 0.25rem;
		--track-border-color: var(--color-input);
		--track-border: 1px solid var(--track-border-color);
	}

	.slider:hover {
		--thumb-color: var(--color-foreground);
		--track-filled: var(--color-foreground);
		--track-unfilled: var(--color-muted);
	}

	.slider:focus,
	.slider:active {
		--thumb-color: var(--color-foreground);
		--track-filled: var(--color-foreground);
		--track-unfilled: var(--color-muted);
		--track-border-color: var(--color-ring);
	}

	.slider::-webkit-slider-runnable-track {
		width: 100%;
		height: var(--track-height);
		background: linear-gradient(
			to right,
			var(--track-filled) 0%,
			var(--track-filled) var(--fill-percentage),
			var(--track-unfilled) var(--fill-percentage),
			var(--track-unfilled) 100%
		);
		border: var(--track-border);
		border-radius: var(--track-radius);
		transition: border-color 150ms ease;
	}

	.slider::-webkit-slider-thumb {
		appearance: none;
		cursor: pointer;
		width: var(--thumb-width);
		height: var(--thumb-height);
		background: var(--thumb-color);
		border-radius: var(--thumb-radius);
		margin-block: calc((var(--thumb-height) - var(--track-height)) * -0.5);
	}

	.slider::-moz-range-track {
		width: 100%;
		height: var(--track-height);
		background: var(--track-unfilled);
		border: var(--track-border);
		border-radius: var(--track-radius);
		transition: border-color 150ms ease;
	}

	.slider::-moz-range-progress {
		height: var(--track-height);
		background: var(--track-filled);
		border-radius: var(--track-radius) 0 0 var(--track-radius);
	}

	.slider::-moz-range-thumb {
		appearance: none;
		width: var(--thumb-width);
		height: var(--thumb-height);
		background: var(--thumb-color);
		border: none;
		border-radius: var(--thumb-radius);
		cursor: pointer;
	}
</style>
