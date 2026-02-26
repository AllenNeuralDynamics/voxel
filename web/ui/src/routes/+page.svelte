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
	import { Select } from '$lib/ui/primitives';
	import { sanitizeString } from '$lib/utils';
	import { LaserIndicators } from '$lib/ui/devices';
	import LasersPanel from './LasersPanel.svelte';
	import CamerasPanel from './CamerasPanel.svelte';
	import SessionPanel from './SessionPanel.svelte';
	import DevicesPanel from './DevicesPanel.svelte';
	import ConfigurePanel from './ConfigurePanel.svelte';
	import WorkflowTabs from '$lib/ui/WorkflowTabs.svelte';
	import { cn } from '$lib/utils';

	let app = $state<App | undefined>(undefined);
	let viewId = $state('scout');

	// Control view state
	let bottomPanelTab = $state('lasers');
	let bottomPane: Pane | undefined = $state(undefined);

	function tabButtonClass(selected: boolean): string {
		return cn(
			'gap-2 flex items-center px-2 py-0.5 text-xs transition-colors hover:bg-muted',
			selected ? 'bg-muted text-foreground' : 'text-muted-foreground'
		);
	}

	function selectBottomTab(tab: string) {
		if (bottomPanelTab === tab) {
			if (bottomPane?.isCollapsed()) bottomPane.expand();
			else bottomPane?.collapse();
		} else {
			bottomPanelTab = tab;
			if (bottomPane?.isCollapsed()) bottomPane.expand();
		}
	}

	function toggleView(id: string) {
		if (viewId === id) {
			viewId = app?.session?.workflow.steps[0]?.id ?? 'scout';
		} else {
			viewId = id;
		}
	}

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

{#snippet tabButton(id: string, label: string)}
	<button onclick={() => selectBottomTab(id)} class={tabButtonClass(bottomPanelTab === id)}>
		{label}
	</button>
{/snippet}

{#if app?.session}
	{@const session = app.session}
	{@const workflow = session.workflow}
	<div class="h-screen w-full bg-background text-foreground">
		<PaneGroup direction="horizontal" autoSaveId="main-h">
			<Pane defaultSize={55} minSize={50} maxSize={70}>
				<!-- Control area: header + main + footer -->
				<div class="grid h-full grid-rows-[auto_1fr_auto] border-r border-border">
					<header class="flex items-center justify-between gap-8 border-b border-border bg-card px-4 py-4">
						<!-- Configure + Workflow + Acquire -->
						<div class="flex flex-1 items-center gap-3">
							<button
								onclick={() => toggleView('configure')}
								class="flex items-center justify-center rounded transition-colors {viewId === 'configure'
									? 'text-foreground'
									: 'text-muted-foreground hover:text-foreground'}"
								title="Configure"
							>
								<Icon icon="mdi:cog" width="16" height="16" />
							</button>
							<WorkflowTabs {workflow} bind:viewId class="max-w-96 min-w-88" />
							<button
								onclick={() => toggleView('acquire')}
								class="flex items-center justify-center rounded transition-colors {viewId === 'acquire'
									? 'text-foreground'
									: 'text-muted-foreground hover:text-foreground'}"
								title="Acquire"
							>
								<Icon icon="mdi:play-circle-outline" width="16" height="16" />
							</button>
						</div>
						<div class="flex items-center gap-4">
							<Button
								class="min-w-26"
								variant={session.preview.isPreviewing ? 'danger' : 'success'}
								size="md"
								onclick={() =>
									session.preview.isPreviewing ? session.preview.stopPreview() : session.preview.startPreview()}
							>
								{session.preview.isPreviewing ? 'Stop Preview' : 'Start Preview'}
							</Button>
							<Select
								value={session.activeProfileId ?? ''}
								options={Object.entries(session.config.profiles).map(([id, cfg]) => ({
									value: id,
									label: cfg.label ?? sanitizeString(id),
									description: cfg.desc
								}))}
								onchange={(v) => session.activateProfile(v)}
								icon="mdi:chevron-up-down"
								loading={session.isMutating}
								showCheckmark
								emptyMessage="No profiles available"
								size="lg"
								class="min-w-56"
							/>
						</div>
					</header>
					<PaneGroup direction="vertical" autoSaveId="midCol-v3">
						<Pane>
							<div class="h-full overflow-auto">
								{#if viewId === 'configure'}
									<ConfigurePanel {session} />
								{:else if viewId === 'scout'}
									<div class="flex h-full flex-col justify-between">
										<div class="p-4">
											<GridControls {session} />
										</div>
									</div>
								{:else if viewId === 'plan'}
									<div class="flex h-full items-center justify-center">
										<p class="text-sm text-muted-foreground">Plan — define stacks for acquisition</p>
									</div>
								{:else if viewId === 'acquire'}
									{#if workflow.allCommitted}
										<div class="flex h-full flex-col justify-between">
											<DevicesPanel {session} class="h-auto" />
										</div>
									{:else}
										<div class="flex h-full items-center justify-center">
											<p class="text-sm text-muted-foreground">Complete all workflow steps before acquiring</p>
										</div>
									{/if}
								{/if}
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
							{#if bottomPanelTab === 'cameras'}
								<CamerasPanel {session} />
							{:else if bottomPanelTab === 'lasers'}
								<LasersPanel {session} />
							{:else if bottomPanelTab === 'waveforms'}
								<div class="h-full overflow-hidden bg-card">
									<WaveformViewer {session} />
								</div>
							{:else if bottomPanelTab === 'logs'}
								<div class="h-full overflow-hidden bg-card p-2">
									<LogViewer logs={app.logs} onClear={() => app?.clearLogs()} />
								</div>
							{:else if bottomPanelTab === 'session'}
								<SessionPanel {session} />
							{/if}
						</Pane>
					</PaneGroup>
					<footer class="flex items-center justify-between border-t border-border px-4 py-2">
						<div class="flex divide-x divide-border rounded border border-border">
							{@render tabButton('cameras', 'Cameras')}
							<button onclick={() => selectBottomTab('lasers')} class={tabButtonClass(bottomPanelTab === 'lasers')}>
								Lasers
								{#if Object.keys(session.lasers).length > 0}
									<LaserIndicators lasers={session.lasers} size="md" />
								{/if}
							</button>
							{@render tabButton('waveforms', 'Waveforms')}
						</div>
						<div class="flex items-center gap-3">
							<div class="flex divide-x divide-border rounded border border-border">
								{@render tabButton('logs', 'Logs')}
								<button onclick={() => selectBottomTab('session')} class={tabButtonClass(bottomPanelTab === 'session')}>
									Session
									<ClientStatus client={app.client} />
								</button>
							</div>
							<div class="h-4 w-px bg-border"></div>
							<button
								onclick={() => app?.closeSession()}
								class="flex cursor-pointer items-center gap-1 rounded border border-border px-1.5 py-0.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
								aria-label="Close Session"
								title="Close Session"
							>
								Exit
								<Icon icon="mdi:logout" width="12" height="12" />
							</button>
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
							<PreviewCanvas previewer={session.preview} />
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
