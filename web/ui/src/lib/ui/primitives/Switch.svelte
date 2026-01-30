<script lang="ts">
	import { Switch as SwitchPrimitive } from 'bits-ui';

	interface Props {
		checked?: boolean;
		onCheckedChange?: (checked: boolean) => void;
		disabled?: boolean;
		class?: string;
	}

	let { checked = $bindable(false), onCheckedChange, disabled = false, class: className = '' }: Props = $props();
</script>

<SwitchPrimitive.Root
	bind:checked
	{onCheckedChange}
	{disabled}
	class="relative h-5 w-10 cursor-pointer rounded-full border border-zinc-600/50 bg-zinc-700/80 transition-colors hover:bg-zinc-700 data-disabled:cursor-not-allowed data-disabled:opacity-40 data-[state=checked]:border-emerald-600 data-[state=checked]:bg-emerald-600/90 data-[state=checked]:hover:bg-emerald-600 {className}"
>
	<SwitchPrimitive.Thumb
		class="block h-3.5 w-3.5 translate-x-0.5 rounded-full bg-zinc-100 transition-transform data-[state=checked]:translate-x-5.5"
	/>
</SwitchPrimitive.Root>
