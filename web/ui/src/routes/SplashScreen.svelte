<script lang="ts">
	import type { App } from '$lib/main';
	import VoxelLogo from '$lib/ui/VoxelLogo.svelte';
	import VoxelPatternBG from '$lib/ui/VoxelPatternBG.svelte';

	const { app }: { app?: App } = $props();
</script>

<div class="relative flex h-screen w-full flex-col items-center justify-center gap-6 bg-background">
	<VoxelPatternBG />
	<div class="relative z-10 flex flex-col items-center gap-6">
		<div class="flex items-center gap-3">
			<VoxelLogo
				class="h-10 w-10"
				topLeft={{ top: '#2EF58D', left: '#22CC75', right: '#189960' }}
				topRight={{ top: '#F52E64', left: '#CC2250', right: '#99193C' }}
				bottom={{ top: '#F5D62E', left: '#CCB222', right: '#998619' }}
			/>
			<h1 class="text-3xl font-light text-foreground uppercase">Voxel</h1>
		</div>

		{#if app?.client.connectionState === 'failed'}
			<div class="flex flex-col items-center gap-3">
				<p class="text-sm text-danger">{app.client.connectionMessage}</p>
				<button
					onclick={() => app.retryConnection()}
					class="rounded border border-input bg-transparent px-4 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
				>
					Retry
				</button>
			</div>
		{:else if app}
			<div class="flex items-center gap-2">
				<div class="size-4 shrink-0 animate-spin rounded-full border-2 border-border border-t-primary"></div>
				<p class="text-xs leading-none text-muted-foreground">{app.client.connectionMessage}</p>
			</div>
		{:else}
			<p class="text-xs text-muted-foreground">Loading...</p>
		{/if}
	</div>
</div>
