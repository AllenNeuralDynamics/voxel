<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { App } from '$lib/main';
	import SplashScreen from './SplashScreen.svelte';
	import LaunchScreen from './LaunchScreen.svelte';
	import { PreviewCanvas } from '$lib/ui/preview';
	import { GridCanvas, GridControls } from '$lib/ui/grid/canvas';
	import LogViewer from '$lib/ui/LogViewer.svelte';
	import WaveformViewer from '$lib/ui/WaveformViewer.svelte';
	import ClientStatus from '$lib/ui/ClientStatus.svelte';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/primitives/PaneDivider.svelte';
	import { Button } from '$lib/ui/primitives';
	import Icon from '@iconify/svelte';
	import { sanitizeString } from '$lib/utils';
	import ProfileSelector from '$lib/ui/ProfileSelector.svelte';
	import { LaserIndicators } from '$lib/ui/devices';
	import DevicesPanel from './DevicesPanel.svelte';
	import LasersPanel from './LasersPanel.svelte';

	let app = $state<App | undefined>(undefined);

	// Control view state
	let bottomPanelTab = $state('lasers');
	let bottomPane: Pane | undefined = $state(undefined);

	function selectBottomTab(tab: string) {
		if (bottomPanelTab === tab) {
			if (bottomPane?.isCollapsed()) bottomPane.expand();
			else bottomPane?.collapse();
		} else {
			bottomPanelTab = tab;
			if (bottomPane?.isCollapsed()) bottomPane.expand();
		}
	}

	// Workflow modes
	type WorkflowMode = 'scout' | 'plan' | 'acquire';
	let workflowMode = $state<WorkflowMode>('scout');
	let completedModes = $state(new Set<WorkflowMode>());

	function cleanup() {
		if (app) {
			app.destroy();
			app = undefined;
		}
	}

	onMount(async () => {
		window.addEventListener('beforeunload', cleanup);
		try {
			app = new App();
			await app.initialize();
		} catch {
			// Connection state managed by client — splash handles the UI
		}
	});

	onDestroy(() => {
		window.removeEventListener('beforeunload', cleanup);
		cleanup();
	});
</script>

{#if app?.session}
	{@const session = app.session}
	{@const activeProfileLabel = (() => {
		const p = session.activeProfile;
		return p ? (p.label ?? p.desc ?? sanitizeString(p.id)) : 'No profile';
	})()}
	<div class="h-screen w-full bg-background text-foreground">
		<PaneGroup direction="horizontal" autoSaveId="main-h">
			<Pane defaultSize={55} minSize={50} maxSize={70}>
				<!-- Control area: header + aside/middle + footer -->
				<div class="flex h-full flex-col border-r border-border">
					<!-- Global header -->
					<header class="flex items-center justify-between border-b border-border bg-card px-4 py-4">
						<div class="flex items-center gap-8">
							<ProfileSelector {session} />
							<div class="flex items-center gap-3">
								{#each [{ id: 'scout', label: 'Scout' }, { id: 'plan', label: 'Plan' }, { id: 'acquire', label: 'Acquire' }] as mode, i (mode.id)}
									{@const isActive = workflowMode === mode.id}
									{@const isComplete = completedModes.has(mode.id as WorkflowMode)}
									{#if i > 0}
										<div class="h-px w-4 bg-border"></div>
									{/if}
									<button
										onclick={() => (workflowMode = mode.id as WorkflowMode)}
										class="flex items-center gap-2 text-xs transition-colors {isActive
											? 'text-foreground'
											: 'text-muted-foreground hover:text-foreground'}"
									>
										<div
											class="flex h-3.5 w-3.5 items-center justify-center rounded-full border transition-colors {isComplete
												? 'border-success bg-success text-white'
												: isActive
													? 'border-foreground'
													: 'border-muted-foreground/50'}"
										>
											{#if isComplete}
												<Icon icon="mdi:check" width="8" height="8" />
											{/if}
										</div>
										<span class:font-medium={isActive}>{mode.label}</span>
									</button>
								{/each}
							</div>
						</div>
						<div class="flex min-w-64 items-center justify-end">
							<Button
								variant={session.previewState.isPreviewing ? 'danger' : 'success'}
								size="sm"
								onclick={() =>
									session.previewState.isPreviewing
										? session.previewState.stopPreview()
										: session.previewState.startPreview()}
							>
								{session.previewState.isPreviewing ? 'Stop Preview' : 'Start Preview'}
							</Button>
						</div>
					</header>

					<!-- Content: aside + middle -->
					<div class="flex flex-1 overflow-hidden">
						<!-- Middle: Acquisition planning -->
						<div class="flex flex-1 flex-col">
							<PaneGroup direction="vertical" autoSaveId="midCol-v3">
								<Pane minSize={30}>
									<div class="h-full overflow-auto">
										<div class="flex">
											<!-- <aside class="flex w-96 min-w-80 flex-col border-r border-border bg-card">
												<ChannelPanel {session} />
											</aside> -->
											{#if workflowMode === 'scout'}
												<div class="flex flex-col p-4">
													<GridControls {session} />
												</div>
											{:else if workflowMode === 'plan'}
												<div class="flex h-full items-center justify-center">
													<p class="text-sm text-muted-foreground">Plan — configure grid and define stacks</p>
												</div>
											{:else if workflowMode === 'acquire'}
												<div class="flex h-full items-center justify-center">
													<p class="text-sm text-muted-foreground">Acquire — run acquisition and monitor progress</p>
												</div>
											{/if}
										</div>
									</div>
								</Pane>
								<PaneDivider direction="horizontal" class="text-border hover:text-muted-foreground" />
								<Pane
									bind:this={bottomPane}
									collapsible
									collapsedSize={0}
									defaultSize={30}
									minSize={30}
									maxSize={50}
									onCollapse={() => {}}
								>
									{#if bottomPanelTab === 'devices'}
										<DevicesPanel {session} />
									{:else if bottomPanelTab === 'session'}
										<div class="h-full overflow-auto bg-card p-4">
											<div class="space-y-4 text-sm text-muted-foreground">
												<h3 class="text-xs font-medium uppercase">Session Info</h3>
												<div class="grid grid-cols-2 gap-2 text-xs">
													<span>Config</span>
													<span class="text-foreground">{session.config.info.name}</span>
													<span>Active profile</span>
													<span class="text-foreground">{activeProfileLabel}</span>
													<span>Tiles</span>
													<span class="text-foreground">{session.tiles.length}</span>
													<span>Stacks</span>
													<span class="text-foreground">{session.stacks.length}</span>
													<span>Stage connected</span>
													<span class="text-foreground">{session.stageConnected ? 'Yes' : 'No'}</span>
												</div>

												<h3 class="text-xs font-medium uppercase">Stage</h3>
												<div class="grid grid-cols-2 gap-2 text-xs">
													<span>X position</span>
													<span class="text-foreground">{session.xAxis.position.toFixed(3)} mm</span>
													<span>Y position</span>
													<span class="text-foreground">{session.yAxis.position.toFixed(3)} mm</span>
													<span>Z position</span>
													<span class="text-foreground">{session.zAxis.position.toFixed(3)} mm</span>
													<span>Moving</span>
													<span class="text-foreground">{session.stageIsMoving ? 'Yes' : 'No'}</span>
												</div>

												<h3 class="text-xs font-medium uppercase">Grid</h3>
												<div class="grid grid-cols-2 gap-2 text-xs">
													<span>Overlap</span>
													<span class="text-foreground">{(session.gridConfig.overlap * 100).toFixed(0)}%</span>
													<span>Tile order</span>
													<span class="text-foreground">{session.tileOrder}</span>
													<span>Grid locked</span>
													<span class="text-foreground">{session.gridLocked ? 'Yes' : 'No'}</span>
													<span>FOV</span>
													<span class="text-foreground"
														>{session.fov.width.toFixed(2)} x {session.fov.height.toFixed(2)} mm</span
													>
												</div>
											</div>
										</div>
									{:else if bottomPanelTab === 'waveforms'}
										<div class="h-full overflow-hidden bg-card">
											<WaveformViewer {session} />
										</div>
									{:else if bottomPanelTab === 'lasers'}
										<LasersPanel {session} />
									{:else if bottomPanelTab === 'logs'}
										<div class="h-full overflow-hidden bg-card p-2">
											<LogViewer logs={app.logs} onClear={() => app?.clearLogs()} />
										</div>
									{/if}
								</Pane>
							</PaneGroup>
							<footer class="flex items-center justify-between border-t border-border px-4 py-2">
								<div class="flex rounded border border-border">
									<button
										onclick={() => selectBottomTab('lasers')}
										class="flex items-center gap-2 px-2 py-0.5 text-xs transition-colors hover:bg-accent {bottomPanelTab ===
										'lasers'
											? 'bg-accent text-foreground'
											: 'text-muted-foreground'}"
									>
										Lasers
										{#if Object.keys(session.lasers).length > 0}
											<LaserIndicators lasers={session.lasers} size="md" />
										{/if}
									</button>
									{#each [{ id: 'devices', label: 'Devices' }, { id: 'waveforms', label: 'Waveforms' }, { id: 'session', label: 'Session' }, { id: 'logs', label: 'Logs' }] as tab (tab.id)}
										<button
											onclick={() => selectBottomTab(tab.id)}
											class="border-l border-border px-2 py-0.5 text-xs transition-colors hover:bg-accent {bottomPanelTab ===
											tab.id
												? 'bg-accent text-foreground'
												: 'text-muted-foreground'}"
										>
											{tab.label}
										</button>
									{/each}
								</div>
								<div class="flex items-center">
									<ClientStatus client={app.client} />
									<div class="flex rounded border border-border">
										<button
											onclick={() => app?.closeSession()}
											class="flex cursor-pointer items-center gap-1 px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
											aria-label="Close Session"
											title="Close Session"
										>
											<Icon icon="mdi:power" width="12" height="12" />
											Exit
										</button>
									</div>
								</div>
							</footer>
						</div>
					</div>
				</div>
			</Pane>

			<PaneDivider direction="vertical" class="text-border hover:text-muted-foreground" />

			<!-- Right column: Viewer (Preview + Grid Canvas) -->
			<Pane defaultSize={45}>
				<main class="flex h-full flex-col overflow-hidden">
					<PaneGroup direction="vertical" autoSaveId="rightCol-v3">
						<Pane defaultSize={50} minSize={30} class="flex flex-1 flex-col justify-center px-4">
							<PreviewCanvas previewer={session.previewState} />
						</Pane>
						<PaneDivider direction="horizontal" class="text-border hover:text-muted-foreground" />
						<Pane defaultSize={50} minSize={30} class="h-full flex-1 px-4">
							<GridCanvas {session} />
						</Pane>
					</PaneGroup>
				</main>
			</Pane>
		</PaneGroup>
	</div>
{:else if app?.status?.phase === 'idle'}
	<LaunchScreen {app} />
{:else}
	<SplashScreen {app} />
{/if}
