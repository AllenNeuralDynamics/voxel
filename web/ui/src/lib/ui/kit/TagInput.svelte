<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const tagInputVariants = tv({
		slots: {
			wrapper: 'flex flex-wrap gap-1',
			chip: ['flex items-center rounded border border-input', 'transition-colors', 'focus-within:border-focused'],
			input: 'bg-transparent outline-none placeholder-fg-muted',
			remove: 'shrink-0 rounded-r text-fg-muted/50 transition-colors hover:text-danger',
			add: [
				'flex items-center justify-center rounded border border-dashed border-input',
				'text-fg-muted/50 transition-colors',
				'hover:border-fg/20 hover:text-fg'
			]
		},
		variants: {
			variant: {
				ghost: {
					chip: 'bg-transparent hover:border-fg/20'
				},
				filled: {
					chip: 'bg-element-bg hover:bg-element-hover'
				}
			},
			size: {
				xs: {
					chip: 'h-ui-xs',
					input: 'px-1.5 text-xs',
					remove: 'px-0.5',
					add: 'size-ui-xs'
				},
				sm: {
					chip: 'h-ui-sm',
					input: 'px-1.5 text-xs',
					remove: 'px-0.5',
					add: 'size-ui-sm'
				},
				md: {
					chip: 'h-ui-md',
					input: 'px-2 text-sm',
					remove: 'px-1',
					add: 'size-ui-md'
				},
				lg: {
					chip: 'h-ui-lg',
					input: 'px-2.5 text-base',
					remove: 'px-1',
					add: 'size-ui-lg'
				}
			}
		},
		defaultVariants: {
			variant: 'filled',
			size: 'md'
		}
	});

	export type TagInputVariants = VariantProps<typeof tagInputVariants>;
</script>

<script lang="ts">
	import { cn } from '$lib/utils';
	import { Close, Plus } from '$lib/icons';
	import { tick } from 'svelte';

	interface Props extends TagInputVariants {
		value: string[];
		disabled?: boolean;
		onChange?: (newValue: string[]) => void;
		class?: string;
	}

	let {
		value = $bindable(),
		disabled = false,
		onChange,
		variant = 'filled',
		size = 'md',
		class: className = ''
	}: Props = $props();

	const styles = $derived(tagInputVariants({ variant, size }));

	const iconSizes: Record<NonNullable<TagInputVariants['size']>, number> = {
		xs: 8,
		sm: 10,
		md: 12,
		lg: 14
	};

	let inputRefs: (HTMLInputElement | null)[] = $state([]);

	function update(next: string[]) {
		value = next;
		onChange?.(next);
	}

	async function addItem() {
		update([...value, '']);
		await tick();
		inputRefs[value.length - 1]?.focus();
	}

	function removeItem(index: number) {
		const next = value.filter((_, i) => i !== index);
		update(next);
		// Focus previous chip, or next, or nothing
		tick().then(() => {
			const target = Math.min(index, next.length - 1);
			if (target >= 0) inputRefs[target]?.focus();
		});
	}

	function updateItem(index: number, val: string) {
		const next = [...value];
		next[index] = val;
		update(next);
	}

	function handleKeydown(index: number, e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			addItem();
		} else if (e.key === 'Backspace' && value[index] === '') {
			e.preventDefault();
			if (value.length > 1) {
				removeItem(index);
			}
		}
	}

	function handleBlur(index: number) {
		// Remove empty items on blur, but keep at least one
		if (value[index] === '' && value.length > 1) {
			removeItem(index);
		}
	}

	// Ensure at least one item when not disabled
	const items = $derived(!disabled && value.length === 0 ? [''] : value);
	$effect(() => {
		if (!disabled && value.length === 0) {
			value = [''];
			onChange?.(['']);
		}
	});
</script>

<div class={cn(styles.wrapper(), className)}>
	{#each items as item, i (i)}
		<div class={cn(styles.chip(), disabled && 'pointer-events-none')}>
			<input
				bind:this={inputRefs[i]}
				type="text"
				value={item}
				{disabled}
				placeholder=""
				oninput={(e) => updateItem(i, e.currentTarget.value)}
				onkeydown={(e) => handleKeydown(i, e)}
				onblur={() => handleBlur(i)}
				style:width="{Math.max(3, item.length) + 1}ch"
				class={styles.input()}
			/>
			<button
				type="button"
				onclick={() => removeItem(i)}
				{disabled}
				class={cn(styles.remove(), disabled && 'pointer-events-none opacity-50')}
			>
				<Close width={iconSizes[size]} height={iconSizes[size]} />
			</button>
		</div>
	{/each}
	{#if !disabled}
		<button type="button" onclick={addItem} class={styles.add()}>
			<Plus width={iconSizes[size]} height={iconSizes[size]} />
		</button>
	{/if}
</div>
