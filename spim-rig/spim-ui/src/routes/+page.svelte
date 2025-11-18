<script lang="ts">
	import { PreviewCanvas, Previewer, PreviewChannelControls, PreviewInfo } from '$lib/preview';
	import { onMount, onDestroy } from 'svelte';
	import { ProfilesManager } from '$lib/profiles.svelte';
	import ProfileSelector from '$lib/ProfileSelector.svelte';
	import { RigClient, ClientStatus } from '$lib/client';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/PaneDivider.svelte';

	// Initialize configuration
	const apiBaseUrl = 'http://localhost:8000';
	const rigSocketUrl = 'ws://localhost:8000/ws/rig';

	// Create single shared RigClient
	let rigClient: RigClient;
	let previewer: Previewer;
	let profilesManager: ProfilesManager;

	onMount(async () => {
		// Create and connect RigClient
		rigClient = new RigClient(rigSocketUrl);

		try {
			await rigClient.connect();
			console.log('[App] RigClient connected');
		} catch (error) {
			console.error('[App] Failed to connect RigClient:', error);
		}

		// Initialize managers with shared client
		profilesManager = new ProfilesManager({
			baseUrl: apiBaseUrl,
			rigClient
		});

		previewer = new Previewer(rigClient);
	});

	onDestroy(() => {
		// Clean up in reverse order
		profilesManager?.destroy();
		previewer?.shutdown();
		rigClient?.destroy();
		console.log('[App] Cleanup complete');
	});

	function handleStartPreview() {
		previewer?.startPreview();
	}

	function handleStopPreview() {
		previewer?.stopPreview();
	}
</script>

<div class="flex h-screen w-full bg-zinc-950 text-zinc-100">
	{#if rigClient && profilesManager && previewer}
		<aside class="flex h-full w-96 flex-col gap-4 border-r border-zinc-800 p-4">
			{#if previewer.channels.length === 0}
				<div class="flex flex-1 items-center justify-center">
					<p class="text-sm text-zinc-500">No channels available</p>
				</div>
			{:else}
				<div class="flex flex-1 flex-col gap-4 overflow-y-auto">
					{#each previewer.channels as channel (channel.idx)}
						{#if channel.name}
							<div class="space-y-2 rounded border border-zinc-700/80 bg-zinc-900/50 px-3 py-2">
								<!-- Preview Section -->
								<PreviewChannelControls {channel} {previewer} />

								<div class="space-y-2 pt-3">
									<!-- Detection Section (placeholder) -->
									<div class="space-y-1">
										<div class="text-[0.75rem] text-zinc-500 uppercase">Detection</div>
										<div class="h-16 py-1">
											<div class="text-[0.6rem] text-zinc-500">Exposure, gain, binning controls...</div>
										</div>
									</div>

									<!-- Illumination Section (placeholder) -->
									<div class="space-y-1">
										<div class="text-[0.75rem] font-semibold text-zinc-500 uppercase">Illumination</div>
										<div class="h-16 py-1">
											<div class="text-[0.6rem] text-zinc-500">Power, focus, shutter controls...</div>
										</div>
									</div>
								</div>
							</div>
						{/if}
					{/each}
				</div>
			{/if}
		</aside>
		<main class="flex h-full flex-1 flex-col overflow-hidden border-0 border-zinc-700">
			<PaneGroup direction="horizontal" autoSaveId="rootPanel">
				<Pane class="flex h-full flex-1 flex-col overflow-hidden">
					<!-- <div class="flex h-full flex-1 flex-col overflow-hidden border-0 border-zinc-700"> -->
					<header class="flex items-center justify-between gap-4 p-4">
						<div class="flex gap-2">
							<button
								onclick={handleStartPreview}
								disabled={previewer.isPreviewing}
								class="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
							>
								Start
							</button>
							<button
								onclick={handleStopPreview}
								disabled={!previewer.isPreviewing}
								class="rounded bg-rose-600 px-3 py-1.5 text-sm font-medium transition-colors hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
							>
								Stop
							</button>
						</div>
						<ProfileSelector manager={profilesManager} />
					</header>
					<div class="flex flex-1">
						<PreviewCanvas {previewer} />
					</div>
					<!-- </div> -->
				</Pane>
				<PaneDivider />
				<Pane defaultSize={20} maxSize={30}></Pane>
			</PaneGroup>
			<footer class="flex items-center justify-between border-t border-zinc-800 px-4 py-3">
				<PreviewInfo {previewer} />
				<ClientStatus client={rigClient} />
			</footer>
		</main>
	{:else}
		<div class="flex h-full w-full items-center justify-center">
			<p class="text-zinc-500">Loading...</p>
		</div>
	{/if}
</div>
