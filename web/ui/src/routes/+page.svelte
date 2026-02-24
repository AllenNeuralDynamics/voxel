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
	import ProfileSelector from '$lib/ui/ProfileSelector.svelte';
	import { LaserIndicators } from '$lib/ui/devices';
	import LasersPanel from './LasersPanel.svelte';
	import CamerasPanel from './CamerasPanel.svelte';
	import SessionPanel from './SessionPanel.svelte';

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
	<div class="h-screen w-full bg-background text-foreground">
		<PaneGroup direction="horizontal" autoSaveId="main-h">
			<Pane defaultSize={55} minSize={50} maxSize={70}>
				<!-- Control area: header + main + footer -->
				<div class="grid h-full grid-rows-[auto_1fr_auto] border-r border-border">
					<header class="flex items-center justify-between border-b border-border bg-card px-4 py-4">
						<div class="flex items-center gap-8">
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
						<div class="flex items-center justify-end gap-4">
							<ProfileSelector {session} />
							<Button
								class="min-w-28"
								variant={session.previewState.isPreviewing ? 'danger' : 'success'}
								size="md"
								onclick={() =>
									session.previewState.isPreviewing
										? session.previewState.stopPreview()
										: session.previewState.startPreview()}
							>
								{session.previewState.isPreviewing ? 'Stop Preview' : 'Start Preview'}
							</Button>
						</div>
					</header>
					<PaneGroup direction="vertical" autoSaveId="midCol-v3">
						<Pane>
							<div class="h-full overflow-auto">
								<div class="flex">
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
							defaultSize={40}
							minSize={30}
							maxSize={50}
							onCollapse={() => {}}
						>
							{#if bottomPanelTab === 'session'}
								<SessionPanel {session} />
							{:else if bottomPanelTab === 'waveforms'}
								<div class="h-full overflow-hidden bg-card">
									<WaveformViewer {session} />
								</div>
							{:else if bottomPanelTab === 'lasers'}
								<LasersPanel {session} />
							{:else if bottomPanelTab === 'cameras'}
								<CamerasPanel {session} />
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
							<button
								onclick={() => selectBottomTab('cameras')}
								class="border-l border-border px-2 py-0.5 text-xs transition-colors hover:bg-accent {bottomPanelTab ===
								'cameras'
									? 'bg-accent text-foreground'
									: 'text-muted-foreground'}"
							>
								Cameras
							</button>
							{#each [{ id: 'waveforms', label: 'Waveforms' }, { id: 'session', label: 'Session' }, { id: 'logs', label: 'Logs' }] as tab (tab.id)}
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
