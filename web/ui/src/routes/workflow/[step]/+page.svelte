<script lang="ts">
	import { page } from '$app/state';
	import { getAppContext } from '$lib/context';
	import ScoutPanel from '../../ScoutPanel.svelte';

	const app = getAppContext();
	const session = $derived(app.session!);
	const stepId = $derived(page.params.step);
</script>

{#if stepId === 'scout'}
	<ScoutPanel {session} />
{:else if stepId === 'plan'}
	<div class="flex h-full items-center justify-center">
		<p class="text-sm text-muted-foreground">Plan — define stacks for acquisition</p>
	</div>
{:else}
	<div class="flex h-full items-center justify-center">
		<p class="text-sm text-muted-foreground">Unknown step: {stepId}</p>
	</div>
{/if}
