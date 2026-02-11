<script lang="ts">
	type Size = 'sm' | 'md' | 'lg';

	interface Props {
		value: string;
		placeholder?: string;
		onChange?: (newValue: string) => void;
		id?: string;
		size?: Size;
		class?: string;
	}

	let { value = $bindable(), placeholder, onChange, id, size = 'md', class: className = '' }: Props = $props();

	function handleInput(event: Event & { currentTarget: HTMLInputElement }) {
		value = event.currentTarget.value;
		if (onChange) {
			onChange(value);
		}
	}

	const sizeClasses: Record<Size, string> = {
		sm: 'h-6 px-1.5 text-[0.65rem]',
		md: 'h-7 px-2 text-xs',
		lg: 'h-8 px-2.5 text-sm'
	};
</script>

<input
	{id}
	type="text"
	bind:value
	{placeholder}
	oninput={handleInput}
	class="w-full rounded border border-input bg-transparent placeholder-muted-foreground transition-colors hover:border-foreground/20 focus:border-ring focus:outline-none {sizeClasses[
		size
	]} {className}"
/>
