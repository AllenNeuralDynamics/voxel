<script lang="ts">
	import { PaneResizer } from 'paneforge';

	interface PaneDividerProps {
		direction?: 'horizontal' | 'vertical';
	}

	let { direction = 'vertical' }: PaneDividerProps = $props();

	const separatorClass = direction === 'vertical' ? 'w-3 flex-col' : 'h-3 flex-row';
	const lineClass = direction === 'vertical' ? 'w-[1px]' : 'h-[1px]';
</script>

<PaneResizer
	class={`${separatorClass} flex items-center justify-center gap-2 text-zinc-800 transition-all duration-300 hover:text-zinc-600`}
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
	<!-- </div> -->
</PaneResizer>

<style>
	.line {
		background-color: currentColor;
		opacity: 0.85;
	}
</style>
