<script lang="ts">
	import { PreviewCanvas } from '$lib/ui/preview';
	import { onMount, onDestroy } from 'svelte';
	import { App } from '$lib/app';
	import { LaunchPage } from '$lib/ui/launch';
	import LogViewer from '$lib/ui/LogViewer.svelte';
	import ProfileSelector from '$lib/ui/ProfileSelector.svelte';
	import DeviceFilterToggle, { type DeviceFilter } from '$lib/ui/DeviceFilterToggle.svelte';
	import ClientStatus from '$lib/ui/ClientStatus.svelte';
	import { GridCanvas, GridPanel, GridTable } from '$lib/ui/grid';
	import StagePosition from '$lib/ui/StagePosition.svelte';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/primitives/PaneDivider.svelte';
	import ChannelSection from '$lib/ui/ChannelSection.svelte';
	import LaserIndicators from '$lib/ui/devices/LaserIndicators.svelte';
	import WaveformViewer from '$lib/ui/WaveformViewer.svelte';
	import { Tabs } from 'bits-ui';
	import Icon from '@iconify/svelte';
	import VoxelLogo from '$lib/ui/VoxelLogo.svelte';
	import VoxelPatternBackground from '$lib/ui/VoxelPatternBackground.svelte';

	// App instance
	let app = $state<App | undefined>(undefined);

	// Control view state
	let deviceFilter = $state<DeviceFilter>('all');
	let showHistograms = $state(true);
	let bottomPanelTab = $state('grid');

	// Derived state from App
	const viewName = $derived.by(() => {
		if (!app) return 'splash';
		if (!app.client.isConnected || !app.status) return 'splash';
		switch (app.status.phase) {
			case 'idle':
				return 'launch';
			case 'launching':
				return 'loading';
			case 'ready':
				return 'control';
		}
	});

	// Cleanup function - must be synchronous for beforeunload
	function cleanup() {
		if (app) {
			app.destroy();
			app = undefined;
		}
	}

	onMount(async () => {
		// Register beforeunload early to catch refreshes during initialization
		window.addEventListener('beforeunload', cleanup);

		try {
			app = new App();
			await app.initialize();
			console.debug('[Page] App initialized');
		} catch {
			// Connection state is managed by the client — splash screen handles the UI
		}
	});

	onDestroy(() => {
		window.removeEventListener('beforeunload', cleanup);
		cleanup();
	});

	function handleStartPreview() {
		app?.previewState?.startPreview();
	}

	function handleStopPreview() {
		app?.previewState?.stopPreview();
	}
</script>

{#if app}
	{#if viewName === 'splash'}
		<div class="relative flex h-screen w-full flex-col items-center justify-center gap-6 bg-background">
			<VoxelPatternBackground />
			<!-- Content (above background layers) -->
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
				{#if app.client.connectionState === 'failed'}
					<div class="flex flex-col items-center gap-3">
						<p class="text-sm text-danger">{app.client.connectionMessage}</p>
						<button
							onclick={() => app?.retryConnection()}
							class="rounded border border-input bg-transparent px-4 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
						>
							Retry
						</button>
					</div>
				{:else}
					<div class="flex items-center gap-2">
						<div class="size-4 shrink-0 animate-spin rounded-full border-2 border-border border-t-primary"></div>
						<p class="text-xs leading-none text-muted-foreground">{app.client.connectionMessage}</p>
					</div>
				{/if}
			</div>
		</div>
	{:else if viewName === 'launch' || viewName === 'loading'}
		<!-- Launch page (includes loading state) -->
		<LaunchPage {app} />
	{:else if viewName === 'control' && app.previewState}
		<!-- Control view -->
		<div class="flex h-screen w-full bg-background text-foreground">
			<aside class="flex h-full w-96 min-w-80 flex-col border-r border-border bg-card">
				<!-- Profile Selector -->
				<div class="space-y-3 border-b border-border p-4">
					<ProfileSelector {app} />
					<div class="flex items-center">
						<div class="flex-1">
							<DeviceFilterToggle bind:value={deviceFilter} onValueChange={(v) => (deviceFilter = v)} />
						</div>
						<div class="mx-2 h-4 w-px bg-border"></div>
						<button
							onclick={() => (showHistograms = !showHistograms)}
							class="flex cursor-pointer items-center justify-center rounded-full p-1 transition-all hover:bg-accent {showHistograms
								? ' text-success '
								: ' text-danger'}"
							aria-label={showHistograms ? 'Hide histograms' : 'Show histograms'}
							title={showHistograms ? 'Hide histograms' : 'Show histograms'}
						>
							<Icon icon="et:bargraph" width="18" height="18" />
						</button>
					</div>
				</div>

				{#if app.previewState.channels.length === 0}
					<div class="flex flex-1 items-center justify-center p-4">
						<p class="text-sm text-muted-foreground">No channels available</p>
					</div>
				{:else}
					<div class="flex flex-1 flex-col overflow-y-auto">
						{#each app.previewState.channels as channel (channel.idx)}
							{#if channel.name}
								<div>
									<ChannelSection
										{channel}
										previewer={app.previewState}
										devices={app.devices}
										{deviceFilter}
										{showHistograms}
										catalog={app.colormapCatalog}
									/>
								</div>
								<div class="border-t border-border"></div>
							{/if}
						{/each}
					</div>
				{/if}
				<footer class="mt-auto flex p-4">
					<ClientStatus client={app.client} />
				</footer>
			</aside>
			<main class="flex h-screen min-w-4xl flex-1 flex-col overflow-hidden">
				<Tabs.Root bind:value={bottomPanelTab} class="flex h-full flex-col">
					<PaneGroup direction="vertical" autoSaveId="centerPanel">
						<Pane>
							<PaneGroup direction="horizontal" autoSaveId="viewPanel">
								<Pane defaultSize={50} minSize={30} class="h-full flex-1 px-4">
									<PreviewCanvas previewer={app.previewState} />
								</Pane>
								<PaneDivider class="text-border hover:text-muted-foreground" />
								<Pane defaultSize={50} minSize={30} class="flex flex-1 flex-col justify-center px-4">
									<GridCanvas {app} />
								</Pane>
							</PaneGroup>
						</Pane>
						<PaneDivider direction="horizontal" class="text-border hover:text-muted-foreground" />
						<Pane defaultSize={40} maxSize={70} minSize={30} class="overflow-hidden">
							<!-- Bottom Panel Tab Content -->
							<Tabs.Content value="grid" class="h-full overflow-hidden bg-card">
								<GridTable {app} />
							</Tabs.Content>

							<Tabs.Content value="waveforms" class="h-full overflow-hidden bg-card">
								<WaveformViewer {app} />
							</Tabs.Content>

							<Tabs.Content value="logs" class="h-full overflow-hidden bg-card p-2">
								{#if app}
									<LogViewer
										logs={app.logs}
										onClear={() => {
											if (app) app.logs = [];
										}}
									/>
								{/if}
							</Tabs.Content>
						</Pane>
					</PaneGroup>
					<footer class="relative flex items-center justify-between border-t border-border px-4 py-3">
						<!-- Tab Switcher & Preview Controls -->
						<div class="flex items-center gap-3">
							<Tabs.List class="flex rounded border border-border">
								<Tabs.Trigger
									value="grid"
									class="px-2 py-0.5 text-xs transition-colors hover:bg-accent data-[state=active]:bg-accent data-[state=active]:text-foreground data-[state=inactive]:text-muted-foreground"
								>
									Grid
								</Tabs.Trigger>
								<Tabs.Trigger
									value="waveforms"
									class="border-l border-border px-2 py-0.5 text-xs transition-colors hover:bg-accent data-[state=active]:bg-accent data-[state=active]:text-foreground data-[state=inactive]:text-muted-foreground"
								>
									Waveforms
								</Tabs.Trigger>
								<Tabs.Trigger
									value="logs"
									class="border-l border-border px-2 py-0.5 text-xs transition-colors hover:bg-accent data-[state=active]:bg-accent data-[state=active]:text-foreground data-[state=inactive]:text-muted-foreground"
								>
									Logs
								</Tabs.Trigger>
							</Tabs.List>
						</div>

						<!-- Laser indicators -->
						<div class="px-4">
							<LaserIndicators {app} />
						</div>

						{#if app.stageConnected}
							<StagePosition {app} />
						{/if}
					</footer>
				</Tabs.Root>
			</main>
			<aside class="flex h-full w-96 min-w-96 flex-col border-l border-border bg-card">
				<header class="flex h-18 items-start justify-start gap-2 p-4">
					<button
						onclick={handleStartPreview}
						disabled={app.previewState.isPreviewing}
						class="rounded bg-success px-3 py-2 text-sm font-medium text-success-fg transition-colors hover:bg-success/90 disabled:cursor-not-allowed disabled:opacity-50"
					>
						Start
					</button>
					<button
						onclick={handleStopPreview}
						disabled={!app.previewState.isPreviewing}
						class="rounded bg-danger px-3 py-2 text-sm font-medium text-danger-fg transition-colors hover:bg-danger/90 disabled:cursor-not-allowed disabled:opacity-50"
					>
						Stop
					</button>
				</header>
				<GridPanel {app} />
				<footer class="mt-auto flex flex-row-reverse justify-between p-4">
					<button
						onclick={() => app?.closeSession()}
						class="flex cursor-pointer items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
						aria-label="Close Session"
						title="Close Session"
					>
						<Icon icon="mdi:exit-to-app" width="20" height="20" />
					</button>
				</footer>
			</aside>
		</div>
	{/if}
{:else}
	<!-- Fallback -->
	<div class="flex h-screen w-full items-center justify-center bg-background text-foreground">
		<p class="text-muted-foreground">Loading...</p>
	</div>
{/if}
