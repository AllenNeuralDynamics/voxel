<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const renameVariants = tv({
		slots: {
			text: 'cursor-text rounded border border-transparent',
			input: [
				'w-full min-w-0 bg-surface outline-none',
				'rounded border border-input',
				'focus:border-focused',
				'aria-invalid:border-danger',
				'transition-colors'
			]
		},
		variants: {
			size: { xs: {}, sm: {}, md: {} }
		},
		compoundSlots: [
			{ slots: ['text', 'input'], size: 'xs', class: '-ml-1 px-1 py-0 text-xs' },
			{ slots: ['text', 'input'], size: 'sm', class: '-ml-1 -mt-0.5 px-1 py-0.5 text-sm' },
			{ slots: ['text', 'input'], size: 'md', class: '-ml-1.5 -mt-0.5 px-1.5 py-0.5 text-base' }
		],
		defaultVariants: { size: 'sm' }
	});

	export type RenameVariants = VariantProps<typeof renameVariants>;
</script>

<script lang="ts">
	import { tick } from 'svelte';
	import { cn } from '$lib/utils';

	interface Props extends RenameVariants {
		/** The current text value. */
		value: string;
		/** HTML tag to render in view mode. */
		tag?: string;
		/** Current mode — bind to control externally. */
		mode?: 'view' | 'edit';
		/** How blur is handled: 'exit' cancels editing, 'none' keeps edit mode. */
		blurBehavior?: 'exit' | 'none';
		/** How text is selected when entering edit mode. */
		selectOnEdit?: 'all' | 'end' | 'start';
		/** Validation function — returning false blocks save and sets aria-invalid. */
		validate?: (value: string) => boolean;
		/** Called on successful save with the new value. */
		onSave?: (value: string) => void;
		/** Called when editing is cancelled. */
		onCancel?: () => void;
		class?: string;
		inputClass?: string;
		textClass?: string;
	}

	let {
		value = $bindable(),
		tag = 'span',
		mode = $bindable<'view' | 'edit'>('view'),
		size = 'sm',
		blurBehavior = 'exit',
		selectOnEdit = 'all',
		validate = (v: string) => v.trim().length > 0,
		onSave,
		onCancel,
		class: className,
		inputClass,
		textClass
	}: Props = $props();

	let editValue = $state('');
	let inputRef = $state<HTMLInputElement | null>(null);

	const styles = $derived(renameVariants({ size }));
	const isValid = $derived(validate(editValue));

	async function startEditing(cursorPos?: number) {
		editValue = value;
		mode = 'edit';
		await tick();
		if (!inputRef) return;
		inputRef.focus();
		if (selectOnEdit === 'all') {
			inputRef.setSelectionRange(0, editValue.length);
		} else if (cursorPos !== undefined) {
			inputRef.setSelectionRange(cursorPos, cursorPos);
		} else if (selectOnEdit === 'start') {
			inputRef.setSelectionRange(0, 0);
		} else {
			inputRef.setSelectionRange(editValue.length, editValue.length);
		}
	}

	function save() {
		if (!isValid || mode !== 'edit') return;
		mode = 'view';
		value = editValue;
		onSave?.(editValue);
	}

	function cancel() {
		if (mode !== 'edit') return;
		mode = 'view';
		editValue = value;
		onCancel?.();
	}

	async function handleTextClick() {
		// Brief delay lets the browser finalize click selection
		await new Promise((r) => setTimeout(r, 0));
		const sel = window.getSelection();
		startEditing(sel?.focusOffset ?? undefined);
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			save();
		}
		if (e.key === 'Escape') {
			e.preventDefault();
			cancel();
		}
	}

	// Sync external mode changes
	$effect(() => {
		if (mode === 'edit' && inputRef === null) {
			startEditing();
		}
	});
</script>

{#if mode === 'edit'}
	<input
		bind:this={inputRef}
		type="text"
		autocomplete="off"
		bind:value={editValue}
		aria-invalid={!isValid || undefined}
		class={cn(styles.input(), className, inputClass)}
		onkeydown={handleKeydown}
		onblur={blurBehavior === 'exit' ? () => cancel() : undefined}
		onclick={(e) => e.stopPropagation()}
	/>
{:else}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<svelte:element this={tag} class={cn(styles.text(), className, textClass)} ondblclick={handleTextClick}>
		{value}
	</svelte:element>
{/if}
