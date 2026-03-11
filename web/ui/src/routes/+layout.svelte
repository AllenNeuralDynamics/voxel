<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import { Toaster } from '$lib/ui/kit';
	import { onMount, onDestroy } from 'svelte';
	import { useEventListener } from 'runed';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { App } from '$lib/main';
	import { setAppContext } from '$lib/context';
	import { PreviewCanvas } from '$lib/ui/preview';
	import { GridCanvas } from '$lib/ui/grid/canvas';
	import LogViewer from '$lib/ui/LogViewer.svelte';
	import ClientStatus from '$lib/ui/ClientStatus.svelte';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import { Button } from '$lib/ui/kit';
	import { Cog, PlayCircleOutline } from '$lib/icons';
	import { ProfileSelector } from '$lib/ui/profile';
	import LasersPanel from './LasersPanel.svelte';
	import CamerasPanel from './CamerasPanel.svelte';
	import SessionPanel from './SessionPanel.svelte';
	import WorkflowTabs from '$lib/ui/WorkflowTabs.svelte';
	import LaunchScreen from './LaunchScreen.svelte';
	import { cn } from '$lib/utils';

	let { children } = $props();

	// --- App lifecycle ---

	const app = new App();
	setAppContext(app);

	function cleanup() {
		app.destroy();
	}

	useEventListener(window, 'beforeunload', cleanup);

	onMount(async () => {
		if ('serviceWorker' in navigator) {
			navigator.serviceWorker.register('/sw.js');
		}
		try {
			await app.initialize();
		} catch {
			// Connection state managed by client — splash handles the UI
		}
	});

	onDestroy(cleanup);

	// --- Shell state (only used when session is active) ---

	const viewId = $derived<string>(
		page.route.id === '/acquire'
			? 'acquire'
			: page.route.id === '/workflow/[step]'
				? (page.params.step ?? 'configure')
				: 'configure'
	);

	function viewPath(id: string): string {
		return id === 'configure' ? '/' : id === 'acquire' ? '/acquire' : `/workflow/${id}`;
	}

	const gotoOpts = { keepFocus: true, noScroll: true } as const;

	function gotoView(id: string) {
		// eslint-disable-next-line svelte/no-navigation-without-resolve
		goto(viewPath(id), gotoOpts);
	}

	function toggleView(id: string) {
		gotoView(viewId === id ? (app.session?.workflow.steps[0]?.id ?? 'configure') : id);
	}

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

	const tabClasses = cn(
		'flex gap-1 items-center justify-center rounded-xl border border-border',
		'px-3 py-1.5 text-[0.65rem] uppercase tracking-wide transition-colors'
	);
</script>

{#snippet tabButton(id: string, label: string)}
	<button onclick={() => selectBottomTab(id)} class={tabButtonClass(bottomPanelTab === id)}>
		{label}
	</button>
{/snippet}

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{#if app.session}
	{@const session = app.session}
	{@const workflow = session.workflow}
	<div class="h-screen w-full bg-background text-foreground">
		<PaneGroup direction="horizontal" autoSaveId="main-h">
			<Pane defaultSize={60} minSize={50} maxSize={70} class="bg-zinc-900">
				<!-- Control area: header + main + footer -->
				<div class="grid h-full grid-rows-[auto_1fr_auto] border-r border-border">
					<header class="flex items-center justify-between gap-8 border-b border-border bg-card px-4 py-4">
						<!-- Configure + Workflow + Acquire -->
						<div class="flex flex-1 items-center gap-3">
							<button
								onclick={() => toggleView('configure')}
								class={cn(
									tabClasses,
									viewId === 'configure' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'
								)}
								title="Configure"
							>
								<Cog width="16" height="16" /> Configure
							</button>
							<WorkflowTabs {workflow} {viewId} onViewChange={gotoView} class="max-w-96" />
							<button
								onclick={() => toggleView('acquire')}
								class={cn(
									tabClasses,
									viewId === 'acquire' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'
								)}
								title="Acquire"
							>
								<PlayCircleOutline width="16" height="16" />
								Acquire
							</button>
						</div>
						<div class="flex items-center gap-3">
							{#if viewId !== 'configure'}
								<ProfileSelector {session} size="lg" class="max-w-64 min-w-56" />
							{/if}
							<Button
								class="min-w-26"
								variant={session.preview.isPreviewing ? 'danger' : 'success'}
								size="md"
								onclick={() =>
									session.preview.isPreviewing ? session.preview.stopPreview() : session.preview.startPreview()}
							>
								{session.preview.isPreviewing ? 'Stop Preview' : 'Start Preview'}
							</Button>
						</div>
					</header>
					<PaneGroup direction="vertical" autoSaveId="midCol-v3">
						<Pane>
							<div class="h-full overflow-auto">
								{@render children()}
							</div>
						</Pane>
						<PaneDivider
							direction="horizontal"
							ondblclick={() => {
								if (bottomPane?.isCollapsed()) bottomPane.expand();
								else bottomPane?.collapse();
							}}
						/>
						<Pane
							bind:this={bottomPane}
							collapsible
							collapsedSize={0}
							defaultSize={30}
							minSize={30}
							maxSize={50}
							onCollapse={() => {}}
						>
							{#if bottomPanelTab === 'cameras'}
								<CamerasPanel {session} />
							{:else if bottomPanelTab === 'lasers'}
								<LasersPanel {session} />
							{:else if bottomPanelTab === 'logs'}
								<div class="h-full overflow-hidden bg-card p-2">
									<LogViewer logs={app.logs} onClear={() => app.clearLogs()} />
								</div>
							{:else if bottomPanelTab === 'session'}
								<SessionPanel {session} onExit={() => app.closeSession()} />
							{/if}
						</Pane>
					</PaneGroup>
					<footer class="flex items-center justify-between border-t border-border px-4 py-2">
						<div class="flex divide-x divide-border rounded border border-border">
							<button onclick={() => selectBottomTab('session')} class={tabButtonClass(bottomPanelTab === 'session')}>
								<ClientStatus client={session.client} />
								Session
							</button>
							{@render tabButton('logs', 'Logs')}
						</div>
						<div class="flex divide-x divide-border rounded border border-border">
							{@render tabButton('cameras', 'Cameras')}
							<button onclick={() => selectBottomTab('lasers')} class={tabButtonClass(bottomPanelTab === 'lasers')}>
								Lasers
								{#each Object.values(session.lasers) as laser (laser.deviceId)}
									<div class="relative">
										{#if laser.isEnabled}
											<div class="h-2 w-2 rounded-full" style="background-color: {laser.color};"></div>
											<span
												class="absolute inset-0 animate-ping rounded-full opacity-75"
												style="background-color: {laser.color};"
											></span>
										{:else}
											<div class="h-2 w-2 rounded-full border opacity-70" style="border-color: {laser.color};"></div>
										{/if}
									</div>
								{/each}
							</button>
						</div>
					</footer>
				</div>
			</Pane>

			<PaneDivider direction="vertical" />

			<!-- Right column: Viewer (Preview + Grid Canvas) -->
			<Pane defaultSize={45}>
				<main class="flex h-full flex-col overflow-hidden">
					<PaneGroup direction="vertical" autoSaveId="rightCol-v3">
						<Pane defaultSize={50} minSize={30} class="flex flex-1 flex-col justify-center px-4">
							<PreviewCanvas previewer={session.preview} />
						</Pane>
						<PaneDivider direction="horizontal" />
						<Pane defaultSize={50} minSize={30} class="h-full flex-1 px-4">
							<GridCanvas {session} />
						</Pane>
					</PaneGroup>
				</main>
			</Pane>
		</PaneGroup>
	</div>
{:else}
	<LaunchScreen {app} />
{/if}
<Toaster position="bottom-right" />
