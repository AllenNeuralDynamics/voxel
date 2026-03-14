<script lang="ts">
	import { PaneResizer } from 'paneforge';

	interface Props {
		direction?: 'vertical' | 'horizontal';
		ondblclick?: () => void;
	}

	let { direction = 'vertical', ondblclick }: Props = $props();
</script>

<PaneResizer class="relative z-50" {ondblclick}>
	<div
		class="hover:bg-border-focused absolute box-content bg-border bg-clip-content transition-colors duration-300
			{direction === 'vertical'
			? 'inset-y-0 left-1/2 w-px -translate-x-1/2 px-1'
			: 'inset-x-0 top-1/2 h-px -translate-y-1/2 py-1'}"
	></div>
</PaneResizer>
