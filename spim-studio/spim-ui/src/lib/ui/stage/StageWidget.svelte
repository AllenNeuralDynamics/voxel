<script lang="ts">
	import type { App } from '$lib/app';
	import StageCanvas from './StageCanvas.svelte';
	import StageControls from './StageControls.svelte';

	interface Props {
		app: App;
	}

	let { app }: Props = $props();

	// Get stage from app
	let stage = $derived(app.stage);
	let isConfigured = $derived(stage !== null);
</script>

{#if isConfigured && stage}
	<div class="flex h-full w-full flex-col">
		<StageCanvas {app} />
		<StageControls {app} />
	</div>
{:else}
	<div class="flex h-full w-full items-center justify-center">
		<p class="text-sm text-zinc-500">Stage not configured</p>
	</div>
{/if}
