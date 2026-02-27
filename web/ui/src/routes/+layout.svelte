<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import { Toaster } from '$lib/ui/kit';
	import { onMount } from 'svelte';

	let { children } = $props();

	onMount(() => {
		if ('serviceWorker' in navigator) {
			navigator.serviceWorker.register('/sw.js');
		}
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{@render children()}
<Toaster position="bottom-right" />
