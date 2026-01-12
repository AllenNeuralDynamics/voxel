<script lang="ts">
	import { PreviewCanvas, PanZoomControls, FrameCounter } from '$lib/preview';
	import { onMount, onDestroy } from 'svelte';
	import { App } from '$lib/app';
	import { LaunchPage } from '$lib/ui/launch';
	import ProfileSelector from '$lib/ui/ProfileSelector.svelte';
	import DeviceFilterToggle, { type DeviceFilter } from '$lib/ui/DeviceFilterToggle.svelte';
	import ClientStatus from '$lib/ui/ClientStatus.svelte';
	import { StagePosition } from '$lib/ui/stage';
	// TODO: StageCanvas and StageControls need to be updated for new Stage/App architecture
	// import { StageCanvas, StageControls } from '$lib/ui/stage';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/primitives/PaneDivider.svelte';
	import ChannelSection from '$lib/ui/ChannelSection.svelte';
	import LaserIndicators from '$lib/ui/devices/LaserIndicators.svelte';
	import WaveformViewer from '$lib/ui/WaveformViewer.svelte';
	import { Tabs } from 'bits-ui';
	import Icon from '@iconify/svelte';

	// App instance
	let app = $state<App | undefined>(undefined);

	// Control view state
	let deviceFilter = $state<DeviceFilter>('all');
	let showHistograms = $state(true);
	let bottomPanelTab = $state('daq');

	// Derived state from App
	const viewName = $derived.by(() => {
		if (!app) return 'connecting';
		if (app.connectionError) return 'error';
		if (!app.status) return 'connecting';
		switch (app.status.phase) {
			case 'idle':
				return 'launch';
			case 'launching':
				return 'loading';
			case 'ready':
				return 'control';
		}
	});
	const previewer = $derived(app?.previewer);
	const stage = $derived(app?.stage);

	onMount(async () => {
		try {
			app = new App();
			await app.initialize();
			console.log('[Page] App initialized');
		} catch (error) {
			console.error('[Page] Initialization failed:', error);
		}
	});

	onDestroy(() => {
		app?.destroy();
		console.log('[Page] Cleanup complete');
	});

	function handleStartPreview() {
		previewer?.startPreview();
	}

	function handleStopPreview() {
		previewer?.stopPreview();
	}
</script>

{#if app}
	{#if viewName === 'connecting'}
		<!-- Connecting to WebSocket -->
		<div class="flex h-screen w-full items-center justify-center bg-zinc-950 text-zinc-100">
			<div class="text-center">
				<div class="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-zinc-700 border-t-blue-500"></div>
				<p class="mt-4 text-zinc-500">Connecting to server...</p>
			</div>
		</div>
	{:else if viewName === 'error'}
		<!-- Error state -->
		<div class="flex h-screen w-full items-center justify-center bg-zinc-950 text-zinc-100">
			<div class="text-center">
				<p class="text-rose-400">{app.connectionError}</p>
				<button
					onclick={() => app?.retryConnection()}
					class="mt-4 rounded bg-zinc-700 px-4 py-2 text-sm transition-colors hover:bg-zinc-600"
				>
					Retry Connection
				</button>
			</div>
		</div>
	{:else if viewName === 'launch' || viewName === 'loading'}
		<!-- Launch page (includes loading state) -->
		<LaunchPage {app} />
	{:else if viewName === 'control' && previewer}
		<!-- Control view -->
		<div class="flex h-screen w-full bg-zinc-950 text-zinc-100">
			<aside class="flex h-full w-96 min-w-80 flex-col border-r border-zinc-700 bg-zinc-900">
				<!-- Profile Selector -->
				<div class="space-y-3 border-b border-zinc-600 p-4">
					<ProfileSelector {app} />
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
									<ChannelSection {channel} {previewer} devices={app.devices} {deviceFilter} {showHistograms} />
								</div>
								<div class="border-t border-zinc-600"></div>
							{/if}
						{/each}
					</div>
				{/if}
				<footer class="mt-auto flex p-4">
					<FrameCounter {previewer} />
				</footer>
			</aside>
			<main class="flex h-screen min-w-4xl flex-1 flex-col overflow-hidden">
				<Tabs.Root bind:value={bottomPanelTab} class="flex h-full flex-col">
					<PaneGroup direction="vertical" autoSaveId="centerPanel">
						<Pane>
							<PaneGroup direction="horizontal" autoSaveId="viewPanel">
								<Pane defaultSize={50} minSize={30} class="grid h-full flex-1 place-content-center px-4">
									<PreviewCanvas {previewer} />
								</Pane>
								<PaneDivider class="text-zinc-700 hover:text-zinc-600" />
								<Pane defaultSize={50} minSize={30} class="flex flex-1 flex-col justify-center px-4">
									<!-- TODO: Update StageCanvas for new Stage/App architecture -->
									<div class="flex h-full items-center justify-center">
										<p class="text-sm text-zinc-500">Stage canvas coming soon...</p>
									</div>
								</Pane>
							</PaneGroup>
						</Pane>
						<PaneDivider direction="horizontal" class="text-zinc-700 hover:text-zinc-600" />
						<Pane defaultSize={40} maxSize={50} minSize={30} class="overflow-hidden">
							<!-- Bottom Panel Tab Content -->
							<Tabs.Content value="grid" class="h-full overflow-auto bg-zinc-900">
								<div class="flex h-full items-center justify-center">
									<p class="text-sm text-zinc-500">Grid view coming soon...</p>
								</div>
							</Tabs.Content>

							<Tabs.Content value="daq" class="h-full overflow-hidden bg-zinc-900">
								<WaveformViewer {app} />
							</Tabs.Content>
						</Pane>
					</PaneGroup>
					<footer class="relative flex items-center justify-between border-t border-zinc-700 px-4 py-3">
						<!-- Tab Switcher & Preview Controls -->
						<div class="flex items-center gap-3">
							<Tabs.List class="flex rounded border border-zinc-700">
								<Tabs.Trigger
									value="grid"
									class="px-2 py-0.5 text-xs transition-colors hover:bg-zinc-800 data-[state=active]:bg-zinc-700 data-[state=active]:text-zinc-100 data-[state=inactive]:text-zinc-400"
								>
									Grid
								</Tabs.Trigger>
								<Tabs.Trigger
									value="daq"
									class="border-l border-zinc-700 px-2 py-0.5 text-xs transition-colors hover:bg-zinc-800 data-[state=active]:bg-zinc-700 data-[state=active]:text-zinc-100 data-[state=inactive]:text-zinc-400"
								>
									DAQ
								</Tabs.Trigger>
							</Tabs.List>

							<PanZoomControls {previewer} />
						</div>

						<!-- Laser indicators -->
						<div class="px-4">
							<LaserIndicators {app} />
						</div>

						{#if stage}
							<StagePosition {stage} />
						{/if}
					</footer>
				</Tabs.Root>
			</main>
			<aside class="flex h-full w-96 min-w-96 flex-col border-l border-zinc-700 bg-zinc-900">
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
					<button
						onclick={() => app?.closeSession()}
						class="ml-auto rounded bg-zinc-700 px-3 py-2 text-sm font-medium transition-colors hover:bg-zinc-600"
					>
						Close Session
					</button>
				</header>
				<!-- TODO: Update StageControls for new Stage/App architecture -->
				<div class="flex flex-1 items-center justify-center">
					<p class="text-sm text-zinc-500">Stage controls coming soon...</p>
				</div>
				<footer class="mt-auto flex flex-row-reverse p-4">
					<ClientStatus client={app.client} />
				</footer>
			</aside>
		</div>
	{/if}
{:else}
	<!-- Fallback -->
	<div class="flex h-screen w-full items-center justify-center bg-zinc-950 text-zinc-100">
		<p class="text-zinc-500">Loading...</p>
	</div>
{/if}
