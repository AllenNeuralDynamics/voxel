<script lang="ts" module>
	let lastWorkflowStep: string | null = null;
</script>

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
	import { Button, Dialog, DropdownMenu } from '$lib/ui/kit';
	import { ChevronDown, ClipboardCheckOutline, LayersOutline, Microscope, Power } from '$lib/icons';
	import AppMenu from './AppMenu.svelte';
	import VoxelLogo from '$lib/ui/VoxelLogo.svelte';
	import StartButton from '$lib/ui/StartButton.svelte';
	import { ProfileSelector } from '$lib/ui/profile';
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
			: page.route.id === '/debug'
				? 'debug'
				: page.route.id?.startsWith('/setup/')
					? 'setup'
					: 'instrument'
	);

	// Remember which workflow step was last viewed
	$effect(() => {
		if (page.route.id?.startsWith('/setup/')) {
			lastWorkflowStep = page.params.step ?? page.route.id.split('/').pop() ?? null;
		}
	});

	function viewPath(id: string): string {
		if (id === 'acquisition') return '/acquisition';
		if (id === 'debug') return '/debug';
		if (id === 'instrument') return '/';
		if (id === 'setup')
			return `/setup/${lastWorkflowStep ?? workflow.activeStep?.id ?? workflow.steps[0]?.id ?? 'scout'}`;
		return `/setup/${id}`;
	}

	function gotoView(id: string) {
		goto(resolve(viewPath(id) as '/'), { keepFocus: true, noScroll: true });
	}

	function selectView(id: string) {
		if (viewId !== id) gotoView(id);
	}

	let closeDialogOpen = $state(false);

	const tabClasses = cn(
		'flex h-ui-lg min-w-24 gap-1.5 items-center justify-center rounded border border-border',
		'px-3 text-base capitalize transition-colors'
	);
</script>

<div class="text-fg h-screen w-full">
	<PaneGroup direction="horizontal" autoSaveId="main-h">
		<Pane defaultSize={60} minSize={50} maxSize={70}>
			<div class="grid h-full grid-rows-[auto_1fr]">
				<header class="bg-elevated flex items-center justify-between border-b border-border px-4 py-4">
					<!-- Left: app menu + instrument + workflow + acquisition -->
					<div class="flex items-stretch gap-4">
						<AppMenu {app}>
							{#snippet trigger()}
								<VoxelLogo class="size-ui-sm" />
								<ChevronDown width="14" height="14" class="text-fg-muted/60 ml-1" />
							{/snippet}
							{#snippet extraItems()}
								<DropdownMenu.Item variant="destructive" onclick={() => (closeDialogOpen = true)}>
									<Power width="14" height="14" />
									Close Session
								</DropdownMenu.Item>
							{/snippet}
						</AppMenu>

						<!-- Close session confirmation dialog -->
						<Dialog.Root bind:open={closeDialogOpen}>
							<Dialog.Content size="sm" showCloseButton={false}>
								<Dialog.Header>
									<Dialog.Title>Close Session</Dialog.Title>
								</Dialog.Header>
								<p class="text-fg-muted text-sm">
									Are you sure you want to close the current session? Any unsaved progress will be lost.
								</p>
								<Dialog.Footer>
									<Dialog.Close>
										<Button variant="ghost">Cancel</Button>
									</Dialog.Close>
									<Button variant="danger" onclick={() => app.closeSession()}>Close Session</Button>
								</Dialog.Footer>
							</Dialog.Content>
						</Dialog.Root>
						<nav class="grid grid-cols-3 gap-4">
							<!-- Instrument -->
							<button
								onclick={() => selectView('instrument')}
								class={cn(
									tabClasses,
									viewId === 'instrument' ? 'text-fg bg-element-bg' : 'text-fg-muted hover:text-fg'
								)}
								title="Instrument"
							>
								<Microscope width="16" height="16" />
								Instrument
							</button>

							<!-- Setup (workflow) -->
							<button
								onclick={() => selectView('setup')}
								class={cn(tabClasses, viewId === 'setup' ? 'text-fg bg-element-bg' : 'text-fg-muted hover:text-fg')}
								title="Setup"
							>
								<ClipboardCheckOutline width="16" height="16" />
								Setup
							</button>

							<!-- Acquire -->
							<button
								onclick={() => selectView('acquisition')}
								class={cn(
									tabClasses,
									viewId === 'acquisition' ? 'text-fg bg-element-bg' : 'text-fg-muted hover:text-fg'
								)}
								title="Acquisition"
							>
								<LayersOutline width="16" height="16" />
								Acquisition
							</button>
						</nav>
					</div>

					<!-- Right: actions -->
					<div class="flex items-center gap-4">
						<button
							onclick={() => selectView('debug')}
							class={cn(tabClasses, viewId === 'debug' ? 'text-fg bg-element-bg' : 'text-fg-muted hover:text-fg')}
							title="Debug"
						>
							Debug
						</button>
						<ProfileSelector {session} size="lg" class="min-w-72 flex-1" />
						<StartButton {session} />
					</div>
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
