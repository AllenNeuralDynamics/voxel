<script lang="ts">
	import { PreviewCanvas, Previewer, PreviewInfo } from '$lib/preview';
	import { onMount, onDestroy } from 'svelte';
	import { RigManager } from '$lib/core';
	import ProfileSelector from '$lib/ProfileSelector.svelte';
	import DeviceFilterToggle, { type DeviceFilter } from '$lib/DeviceFilterToggle.svelte';
	import ClientStatus from '$lib/ClientStatus.svelte';
	import StagePosition from '$lib/StagePosition.svelte';
	import StageWidget from '$lib/StageWidget.svelte';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/PaneDivider.svelte';
	import ChannelSection from '$lib/ChannelSection.svelte';
	import Icon from '@iconify/svelte';
	import { browser } from '$app/environment';

	// Configuration
	const apiBaseUrl = browser ? window.location.origin : 'http://localhost:8000';
	const rigSocketUrl = browser
		? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/rig`
		: 'ws://localhost:8000/ws/rig';

	// Component-level state
	let rigManager = $state<RigManager | undefined>(undefined);
	let previewer = $state<Previewer | undefined>(undefined);
	let deviceFilter = $state<DeviceFilter>('summary');
	let showHistograms = $state(true);

	onMount(async () => {
		try {
			// 1. Create and initialize RigManager (owns RigClient + DevicesManager, fetches config)
			rigManager = new RigManager({
				socketUrl: rigSocketUrl,
				baseUrl: apiBaseUrl
			});
			await rigManager.initialize();
			console.log('[Page] RigManager initialized (includes devices)');

			// 2. Initialize Previewer
			previewer = new Previewer(rigManager);

			console.log('[Page] All managers initialized');
		} catch (error) {
			console.error('[Page] Initialization failed:', error);
		}
	});

	onDestroy(() => {
		// Clean up in reverse order
		previewer?.shutdown();
		rigManager?.destroy();
		console.log('[Page] Cleanup complete');
	});

	function handleStartPreview() {
		previewer?.startPreview();
	}

	function handleStopPreview() {
		previewer?.stopPreview();
	}
</script>

<div class="flex h-screen w-full bg-zinc-950 text-zinc-100">
	{#if previewer && rigManager}
		<aside class="flex h-full w-96 flex-col border-r border-zinc-700 bg-zinc-900">
			<!-- Profile Selector -->
			<div class="space-y-3 border-b border-zinc-600 p-4">
				<ProfileSelector manager={rigManager} />
				<div class="flex items-center">
					<div class="flex-1">
						<DeviceFilterToggle bind:value={deviceFilter} onValueChange={(v) => (deviceFilter = v)} />
					</div>
					<div class="mx-2 h-4 w-px bg-zinc-600"></div>
					<button
						onclick={() => (showHistograms = !showHistograms)}
						class="flex cursor-pointer items-center justify-center rounded-full p-1 transition-all hover:bg-zinc-800 {showHistograms
							? ' text-emerald-400 '
							: ' text-rose-400'}"
						aria-label={showHistograms ? 'Hide histograms' : 'Show histograms'}
						title={showHistograms ? 'Hide histograms' : 'Show histograms'}
					>
						<Icon icon="et:bargraph" width="18" height="18" />
					</button>
				</div>
			</div>

			{#if previewer.channels.length === 0}
				<div class="flex flex-1 items-center justify-center p-4">
					<p class="text-sm text-zinc-500">No channels available</p>
				</div>
			{:else}
				<div class="flex flex-1 flex-col overflow-y-auto">
					{#each previewer.channels as channel (channel.idx)}
						{#if channel.name}
							<div>
								<ChannelSection {channel} {previewer} devices={rigManager.devices} {deviceFilter} {showHistograms} />
							</div>
							<div class="border-t border-zinc-600"></div>
						{/if}
					{/each}
				</div>
			{/if}
		</aside>
		<main class="flex h-screen flex-1 flex-col overflow-hidden">
			<!-- <PaneGroup direction="horizontal" autoSaveId="rootPanel">
				<Pane>
					<PaneGroup direction="vertical" autoSaveId="centerPanel">
						<Pane>
							<PaneGroup direction="horizontal" autoSaveId="viewPanel">
								<Pane class="flex h-full flex-1 flex-col">
									<header class="flex h-18 items-start justify-start gap-2 p-4">
										<button
											onclick={handleStartPreview}
											disabled={previewer.isPreviewing}
											class="rounded bg-emerald-600 px-3 py-2 text-sm font-medium transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
										>
											Start
										</button>
										<button
											onclick={handleStopPreview}
											disabled={!previewer.isPreviewing}
											class="rounded bg-rose-600 px-3 py-2 text-sm font-medium transition-colors hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
										>
											Stop
										</button>
									</header>
									<div class="flex flex-1 flex-col items-start px-4">
										<PreviewCanvas {previewer} />
									</div>
								</Pane>
								<PaneDivider class="text-zinc-700 hover:text-zinc-600" />
								<Pane defaultSize={50} minSize={30} maxSize={50} class=" bg-zinc-950">
									<StageWidget manager={rigManager} {previewer} />
								</Pane>
							</PaneGroup></Pane
						>
						<PaneDivider direction="horizontal" class="text-zinc-700 hover:text-zinc-600" />
						<Pane></Pane>
					</PaneGroup>
				</Pane>
				<Pane>

				</Pane>
			</PaneGroup> -->
			<PaneGroup direction="vertical" autoSaveId="centerPanel">
				<Pane>
					<PaneGroup direction="horizontal" autoSaveId="viewPanel">
						<Pane class="flex h-full flex-1 flex-col">
							<div class="flex flex-1 flex-col items-start px-4">
								<PreviewCanvas {previewer} />
							</div>
						</Pane>
						<PaneDivider class="text-zinc-700 hover:text-zinc-600" />
						<Pane defaultSize={50} minSize={30} maxSize={50} class=" bg-zinc-950">
							<StageWidget manager={rigManager} {previewer} />
						</Pane>
					</PaneGroup>
				</Pane>
				<PaneDivider direction="horizontal" class="text-zinc-700 hover:text-zinc-600" />
				<Pane defaultSize={30}></Pane>
			</PaneGroup>
			<footer class="flex items-center justify-between border-t border-zinc-800 px-4 py-3">
				<PreviewInfo {previewer} />
				<StagePosition manager={rigManager} />
			</footer>
		</main>
		<aside class="flex h-full w-96 flex-col border-r border-zinc-700 bg-zinc-900">
			<header class="flex h-18 items-start justify-start gap-2 p-4">
				<button
					onclick={handleStartPreview}
					disabled={previewer.isPreviewing}
					class="rounded bg-emerald-600 px-3 py-2 text-sm font-medium transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
				>
					Start
				</button>
				<button
					onclick={handleStopPreview}
					disabled={!previewer.isPreviewing}
					class="rounded bg-rose-600 px-3 py-2 text-sm font-medium transition-colors hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
				>
					Stop
				</button>
			</header>
			<footer class="mt-auto flex flex-row-reverse p-4">
				<ClientStatus client={rigManager.client} />
			</footer>
		</aside>
	{:else}
		<div class="flex h-full w-full items-center justify-center">
			<p class="text-zinc-500">Loading...</p>
		</div>
	{/if}
</div>
