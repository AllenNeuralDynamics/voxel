<script lang="ts">
	import type { Snippet } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import type { App, Session } from '$lib/main';
	import { setSessionContext, setLogsContext } from '$lib/context';
	import { PreviewCanvas } from '$lib/ui/preview';
	import { GridCanvas } from '$lib/ui/grid';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import { Button, Dialog } from '$lib/ui/kit';
	import { AlertCircleOutline, LayersOutline, Microscope, Power } from '$lib/icons';
	import WorkflowTabs from './WorkflowTabs.svelte';
	import { cn } from '$lib/utils';

	interface Props {
		app: App;
		session: Session;
		children: Snippet;
	}

	let { app, session, children }: Props = $props();

	// --- Set contexts (runs during component init, safe for setContext) ---

	setSessionContext(() => session);
	setLogsContext({
		get logs() {
			return app.logs;
		},
		clearLogs: () => app.clearLogs()
	});

	// --- Shell state ---

	const workflow = $derived(session.workflow);

	const viewId = $derived<string>(
		page.route.id === '/acquisition'
			? 'acquisition'
			: page.route.id?.startsWith('/workflow/')
				? (page.params.step ?? page.route.id.split('/').pop() ?? 'instrument')
				: 'instrument'
	);

	function viewPath(id: string): string {
		return id === 'instrument' ? '/' : id === 'acquisition' ? '/acquisition' : `/workflow/${id}`;
	}

	function gotoView(id: string) {
		goto(resolve(viewPath(id) as '/'), { keepFocus: true, noScroll: true });
	}

	function toggleView(id: string) {
		gotoView(viewId === id ? (workflow.steps[0]?.id ?? 'instrument') : id);
	}

	const connectionStatus = $derived.by(() => {
		const state = session.client.connectionState ?? 'idle';
		switch (state) {
			case 'connected':
				return { color: 'text-muted-foreground', label: 'Connected', message: '' };
			case 'connecting':
			case 'reconnecting':
				return {
					color: 'text-warning',
					label: state === 'connecting' ? 'Connecting' : 'Reconnecting',
					message: session.client.connectionMessage ?? ''
				};
			case 'failed':
				return {
					color: 'text-danger',
					label: 'Connection Failed',
					message: session.client.connectionMessage ?? ''
				};
			default:
				return { color: 'text-muted-foreground', label: 'Offline', message: '' };
		}
	});

	const tabClasses = cn(
		'flex min-w-24 gap-1 items-center justify-center rounded border border-border',
		'px-3 py-1.5 text-[0.65rem] uppercase tracking-wide transition-colors'
	);
</script>

<div class="h-screen w-full bg-background text-foreground">
	<PaneGroup direction="horizontal" autoSaveId="main-h">
		<Pane defaultSize={60} minSize={50} maxSize={70} class="bg-zinc-900">
			<div class="grid h-full grid-rows-[auto_1fr] border-r border-border">
				<header class="flex items-center justify-between border-b border-border bg-card px-2 py-4">
					<!-- Left: session + instrument + workflow + acquisition -->
					<nav class="flex items-center gap-4">
						<!-- Session power -->
						<Dialog.Root>
							<Dialog.Trigger class={cn(tabClasses, 'min-w-0 cursor-pointer')} title={connectionStatus.label}>
								{#if session.client.connectionState === 'failed'}
									<AlertCircleOutline width="14" height="14" class={connectionStatus.color} />
								{:else}
									<Power width="14" height="14" class={connectionStatus.color} />
								{/if}
							</Dialog.Trigger>
							<Dialog.Content size="sm" showCloseButton={false}>
								<Dialog.Header>
									<Dialog.Title>Session</Dialog.Title>
									<Dialog.Description>
										<span class="flex items-center gap-2">
											<span
												class="inline-block h-2 w-2 rounded-full {connectionStatus.color === 'text-warning'
													? 'bg-warning'
													: connectionStatus.color === 'text-danger'
														? 'bg-danger'
														: 'bg-success'}"
											></span>
											{connectionStatus.label}{#if connectionStatus.message}
												&mdash; {connectionStatus.message}{/if}
										</span>
									</Dialog.Description>
								</Dialog.Header>
								<p class="text-xs text-muted-foreground">
									Are you sure you want to close the current session? Any unsaved progress will be lost.
								</p>
								<Dialog.Footer>
									<Dialog.Close>
										<Button variant="ghost" size="sm">Cancel</Button>
									</Dialog.Close>
									<Button variant="danger" size="sm" onclick={() => app.closeSession()}>Close Session</Button>
								</Dialog.Footer>
							</Dialog.Content>
						</Dialog.Root>

						<!-- Instrument -->
						<button
							onclick={() => toggleView('instrument')}
							class={cn(
								tabClasses,
								viewId === 'instrument' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'
							)}
							title="Instrument"
						>
							<Microscope width="16" height="16" />
							Instrument
						</button>

						<!-- Workflow steps -->
						<WorkflowTabs {workflow} {viewId} onViewChange={gotoView} class="max-w-96" />

						<!-- Acquire -->
						<button
							onclick={() => toggleView('acquisition')}
							class={cn(
								tabClasses,
								viewId === 'acquisition' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'
							)}
							title="Acquisition"
						>
							<LayersOutline width="16" height="16" />
							Acquisition
						</button>
					</nav>

					<!-- Right: Preview -->
					<Button
						class="min-w-26"
						variant={session.preview.isPreviewing ? 'danger' : 'success'}
						size="md"
						onclick={() =>
							session.preview.isPreviewing ? session.preview.stopPreview() : session.preview.startPreview()}
					>
						{session.preview.isPreviewing ? 'Stop Preview' : 'Start Preview'}
					</Button>
				</header>
				{@render children()}
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
