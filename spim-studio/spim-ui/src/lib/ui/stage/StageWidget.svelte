<script lang="ts">
	import type { App } from '$lib/app';
	// TODO: Update StageCanvas and StageControls for new Stage/App architecture
	// import StageCanvas from './StageCanvas.svelte';
	// import StageControls from './StageControls.svelte';

	interface Props {
		app: App;
	}

	let { app }: Props = $props();

	// Get stage from app
	let stage = $derived(app.stage);
	let isConfigured = $derived(stage !== null);
</script>

{#if isConfigured && stage}
	<div class="flex h-full w-full flex-col items-center justify-start">
		<div class="w-full max-w-2xl pt-4">
			<!-- TODO: Update these components for new Stage/App architecture -->
			<div class="flex h-64 items-center justify-center rounded border border-zinc-700">
				<p class="text-sm text-zinc-500">Stage visualization coming soon...</p>
			</div>
		</div>
	</div>
{:else}
	<div class="flex h-full w-full items-center justify-center">
		<p class="text-sm text-zinc-500">Stage not configured</p>
	</div>
{/if}
