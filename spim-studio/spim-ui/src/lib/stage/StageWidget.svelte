<script lang="ts">
	import type { Stage } from './stage.svelte.ts';
	import StageCanvas from './StageCanvas.svelte';
	import StageControls from './StageControls.svelte';
	import { onMount } from 'svelte';

	interface Props {
		stage: Stage;
	}

	let { stage }: Props = $props();

	// Clamp grid cells when max changes
	$effect(() => {
		stage.clampGridCells();
	});

	// Cleanup on unmount
	onMount(() => {
		return () => {
			stage.destroy();
		};
	});

	// Derived check for configuration
	let isConfigured = $derived(stage.config && stage.xAxis && stage.yAxis && stage.zAxis);
</script>

{#if isConfigured}
	<div class="flex h-full w-full flex-col items-center justify-start">
		<div class="w-full max-w-2xl pt-4">
			<StageCanvas {stage} />
			<StageControls {stage} />
		</div>
	</div>
{:else}
	<div class="flex h-full w-full items-center justify-center">
		<p class="text-sm text-zinc-500">Stage not configured</p>
	</div>
{/if}
