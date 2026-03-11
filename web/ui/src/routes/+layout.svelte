<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import { Toaster } from '$lib/ui/kit';
	import { onMount, onDestroy } from 'svelte';
	import { useEventListener } from 'runed';
	import { App } from '$lib/main';
	import { setAppContext } from '$lib/context';
	import LaunchScreen from './LaunchScreen.svelte';

	let { children } = $props();

	const app = new App();
	setAppContext(app);

	function cleanup() {
		app.destroy();
	}

	useEventListener(window, 'beforeunload', cleanup);

	onMount(async () => {
		if ('serviceWorker' in navigator) {
			navigator.serviceWorker.register('/sw.js');
		}
		try {
			await app.initialize();
		} catch {
			// Connection state managed by client — splash handles the UI
		}
	});

	onDestroy(cleanup);
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{#if app.session}
	{@render children()}
{:else}
	<LaunchScreen {app} />
{/if}
<Toaster position="bottom-right" />
