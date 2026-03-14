<script lang="ts">
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import { Toaster } from '$lib/ui/kit';
	import { onMount, onDestroy } from 'svelte';
	import { useEventListener } from 'runed';
	import { App } from '$lib/main';
	import SessionShell from './SessionShell.svelte';
	import LaunchScreen from './LaunchScreen.svelte';

	let { children } = $props();

	// --- App lifecycle ---

	const app = new App();

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
	<SessionShell {app} session={app.session}>
		{@render children()}
	</SessionShell>
{:else}
	<LaunchScreen {app} />
{/if}
<Toaster position="bottom-left" />
