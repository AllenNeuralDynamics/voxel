<script lang="ts">
	import { PreviewCanvas } from '$lib/ui/preview';
	import { onMount, onDestroy } from 'svelte';
	import { App } from '$lib/main';
	import LaunchScreen from '../LaunchScreen.svelte';
	import LogViewer from '$lib/ui/LogViewer.svelte';
	import LeftPanel from '../LeftPanel.svelte';
	import { GridEditor, GridTable } from '$lib/ui/grid';
	import { GridCanvas2 as GridCanvas } from '$lib/ui/grid/canvas';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/primitives/PaneDivider.svelte';
	import LaserIndicators from '$lib/ui/devices/LaserIndicators.svelte';
	import WaveformViewer from '$lib/ui/WaveformViewer.svelte';
	import { Tabs } from 'bits-ui';
	import Icon from '@iconify/svelte';
	import VoxelLogo from '$lib/ui/VoxelLogo.svelte';
	import VoxelPatternBG from '$lib/ui/VoxelPatternBG.svelte';

	// App instance
	let app = $state<App | undefined>(undefined);

	// Control view state
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
</script>

{#if app}
	{#if viewName === 'splash'}
		<div class="relative flex h-screen w-full flex-col items-center justify-center gap-6 bg-background">
			<VoxelPatternBG />
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
		<LaunchScreen {app} />
	{:else if viewName === 'control' && app.session}
		{@const session = app.session}
		<!-- Control view -->
		<div class="flex h-screen w-full bg-background text-foreground">
			<LeftPanel {session} />
			<main class="flex h-screen min-w-4xl flex-1 flex-col overflow-hidden">
				<Tabs.Root bind:value={bottomPanelTab} class="flex h-full flex-col">
					<PaneGroup direction="vertical" autoSaveId="centerPanel">
						<Pane>
							<PaneGroup direction="horizontal" autoSaveId="viewPanel">
								<Pane defaultSize={50} minSize={30} class="h-full flex-1 px-4">
									<PreviewCanvas previewer={session.previewState} />
								</Pane>
								<PaneDivider class="text-border hover:text-muted-foreground" />
								<Pane defaultSize={50} minSize={30} class="flex flex-1 flex-col justify-center px-4">
									<GridCanvas {session} />
								</Pane>
							</PaneGroup>
						</Pane>
						<PaneDivider direction="horizontal" class="text-border hover:text-muted-foreground" />
						<Pane defaultSize={40} maxSize={70} minSize={30} class="overflow-hidden">
							<!-- Bottom Panel Tab Content -->
							<Tabs.Content value="grid" class="h-full overflow-hidden bg-card">
								<PaneGroup direction="horizontal" autoSaveId="gridEditor">
									<Pane minSize={40} class="overflow-hidden">
										<GridTable {session} />
									</Pane>
									<PaneDivider class="text-border hover:text-muted-foreground" />
									<Pane defaultSize={30} minSize={20} maxSize={50} class="overflow-y-auto bg-card">
										<div class="flex flex-col justify-between">
											<GridEditor {session} />
										</div>
									</Pane>
								</PaneGroup>
							</Tabs.Content>

							<Tabs.Content value="waveforms" class="h-full overflow-hidden bg-card">
								<WaveformViewer {session} />
							</Tabs.Content>

							<Tabs.Content value="logs" class="h-full overflow-hidden bg-card p-2">
								{#if app}
									<LogViewer
										logs={app.logs}
										onClear={() => {
											if (app) app.clearLogs();
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

						<div class="flex items-center gap-3">
							<LaserIndicators {session} />
							<button
								onclick={() => app?.closeSession()}
								class="flex cursor-pointer items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
								aria-label="Close Session"
								title="Close Session"
							>
								<Icon icon="mdi:exit-to-app" width="20" height="20" />
							</button>
						</div>
					</footer>
				</Tabs.Root>
			</main>
		</div>
	{/if}
{:else}
	<!-- Fallback -->
	<div class="flex h-screen w-full items-center justify-center bg-background text-foreground">
		<p class="text-muted-foreground">Loading...</p>
	</div>
{/if}
