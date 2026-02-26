<script lang="ts">
	import type { App } from '$lib/main';
	import VoxelLogo from '$lib/ui/VoxelLogo.svelte';

	const { app }: { app?: App } = $props();
</script>

{#snippet voxelPatternBG()}
	<div class="pointer-events-none absolute inset-0">
		<svg class="absolute inset-0 h-full w-full" aria-hidden="true">
			<defs>
				<pattern id="voxel-bg" width={48} height={48} patternUnits="userSpaceOnUse">
					<svg viewBox="-7 -5 360 360" width={48} height={48}>
						<g fill="none" stroke="var(--border)" stroke-width="6" opacity={0.5}>
							<polygon points="86.6,0 173.2,50 86.6,100 0,50" />
							<polygon points="0,50 86.6,100 86.6,200 0,150" />
							<polygon points="86.6,100 173.2,50 173.2,150 86.6,200" />
							<polygon points="259.8,0 346.4,50 259.8,100 173.2,50" />
							<polygon points="173.2,50 259.8,100 259.8,200 173.2,150" />
							<polygon points="259.8,100 346.4,50 346.4,150 259.8,200" />
							<polygon points="173.2,150 259.8,200 173.2,250 86.6,200" />
							<polygon points="86.6,200 173.2,250 173.2,350 86.6,300" />
							<polygon points="173.2,250 259.8,200 259.8,300 173.2,350" />
						</g>
					</svg>
				</pattern>
			</defs>
			<rect width="100%" height="100%" fill="url(#voxel-bg)" />
		</svg>
		<div
			class="absolute inset-0"
			style="background: radial-gradient(ellipse at center, transparent 0%, var(--background) 60%);"
		></div>
	</div>
{/snippet}

<div class="relative flex h-screen w-full flex-col items-center justify-center gap-6 bg-background">
	{@render voxelPatternBG()}
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
