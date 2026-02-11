<script lang="ts">
	import { PaneResizer } from 'paneforge';

	interface PaneDividerProps {
		direction?: 'horizontal' | 'vertical';
		class?: string;
	}

	let { direction = 'vertical', class: className = '' }: PaneDividerProps = $props();

	const separatorClass = $derived(direction === 'vertical' ? 'w-3 flex-col' : 'h-3 flex-row');
	const lineClass = $derived(direction === 'vertical' ? 'w-[1px]' : 'h-[1px]');
	const positionClass = $derived(
		direction === 'vertical' ? 'left-1/2 top-0 bottom-0 -translate-x-1/2' : 'top-1/2 left-0 right-0 -translate-y-1/2'
	);
</script>

<PaneResizer class="relative z-50">
	<div
		class={`absolute flex items-center justify-center gap-2 transition-all duration-300 ${separatorClass} ${positionClass} ${className || 'text-zinc-800 hover:text-zinc-600'}`}
	>
		<div class={`line grow ${lineClass}`}></div>
		<svg
			xmlns="http://www.w3.org/2000/svg"
			width="1.2em"
			height="1.2em"
			viewBox="0 0 15 15"
			fill-rule="evenodd"
			fill="currentColor"
			clip-rule="evenodd"
		>
			{#if direction === 'vertical'}
				<path
					d="M8.625 2.5a1.125 1.125 0 1 1-2.25 0a1.125 1.125 0 0 1 2.25 0m0 5a1.125 1.125 0 1 1-2.25 0a1.125 1.125 0 0 1 2.25 0M7.5 13.625a1.125 1.125 0 1 0 0-2.25a1.125 1.125 0 0 0 0 2.25"
				/>
			{:else}
				<path
					d="M3.625 7.5a1.125 1.125 0 1 1-2.25 0a1.125 1.125 0 0 1 2.25 0m5 0a1.125 1.125 0 1 1-2.25 0a1.125 1.125 0 0 1 2.25 0M12.5 8.625a1.125 1.125 0 1 0 0-2.25a1.125 1.125 0 0 0 0 2.25"
				/>
			{/if}
		</svg>
		<div class={`line grow ${lineClass}`}></div>
	</div>
</PaneResizer>

<style>
	.line {
		background-color: currentColor;
		opacity: 0.85;
	}
</style>
