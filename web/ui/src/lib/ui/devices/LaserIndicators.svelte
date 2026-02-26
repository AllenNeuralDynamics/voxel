<script lang="ts">
	import type { Laser } from '$lib/main';

	interface Props {
		lasers: Record<string, Laser>;
		size?: 'sm' | 'md';
	}

	let { lasers, size = 'sm' }: Props = $props();

	const sizeClass = $derived(size === 'md' ? 'h-2 w-2' : 'h-1.5 w-1.5');
</script>

{#each Object.values(lasers) as laser (laser.deviceId)}
	<div class="relative">
		{#if laser.isEnabled}
			<div class="{sizeClass} rounded-full" style="background-color: {laser.color};"></div>
			<span class="absolute inset-0 animate-ping rounded-full opacity-75" style="background-color: {laser.color};"
			></span>
		{:else}
			<div class="{sizeClass} rounded-full border opacity-70" style="border-color: {laser.color};"></div>
		{/if}
	</div>
{/each}
