<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from '@iconify/svelte';

	interface Props {
		label: string;
		summaryValue: string;
		children: Snippet;
		open?: boolean;
		chevronIcon?: string;
	}

	let { label, summaryValue, children, open = false, chevronIcon = 'mdi:chevron-right' }: Props = $props();
</script>

<details class="card-accordion border-t border-zinc-700" {open}>
	<summary
		class="flex cursor-pointer items-center justify-between px-3 py-2 font-mono text-xs transition-colors hover:bg-zinc-700/30"
	>
		<div class="flex items-center gap-1">
			<span class="accordion-label">{label}</span>
			<Icon icon={chevronIcon} class="chevron text-zinc-500 transition-transform" />
		</div>
		<span class="accordion-value">{summaryValue}</span>
	</summary>

	<div class="content space-y-2 bg-zinc-800/40 px-3 pb-2 text-xs">
		{@render children()}
	</div>
</details>

<style>
	.card-accordion[open] :global(.chevron) {
		transform: rotate(90deg);
	}

	.accordion-label {
		font-size: var(--accordion-label-size, 0.65rem);
		font-weight: var(--accordion-label-weight, 500);
		color: var(--accordion-label-color, var(--color-zinc-400));
	}

	.accordion-value {
		font-size: var(--accordion-value-size, 0.6rem);
		color: var(--accordion-value-color, rgb(212 212 216));
	}

	/* Apply same styling to content children with .label and .value classes */
	.content :global(.label) {
		font-size: var(--accordion-label-size, 0.65rem);
		font-weight: var(--accordion-label-weight, 500);
		color: var(--accordion-label-color, var(--color-zinc-400));
	}

	.content :global(.value) {
		font-size: var(--accordion-value-size, 0.6rem);
		color: var(--accordion-value-color, rgb(212 212 216));
	}
</style>
