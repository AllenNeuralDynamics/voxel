<script lang="ts">
	import type { Component, Snippet } from 'svelte';
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
	import { ChevronDown, Crosshair, Play, Microscope, Power } from '$lib/icons';
	import AppMenu from './AppMenu.svelte';
	import VoxelLogo from '$lib/ui/VoxelLogo.svelte';
	import StartButton from '$lib/ui/StartButton.svelte';
	import { ProfileSelector } from '$lib/ui/profile';
	import { cn } from '$lib/utils';
	import type { Pathname } from '$app/types';
	import { lastInstrumentPath } from './(instrument)/+layout.svelte';

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

	const navTabs: { id: Pathname; label: string; icon: Component }[] = [
		{ id: '/', label: 'Instrument', icon: Microscope },
		{ id: '/setup', label: 'Prepare', icon: Crosshair },
		{ id: '/acquisition', label: 'Acquire', icon: Play }
	];

	const viewId = $derived<Pathname>(
		page.url.pathname.startsWith('/setup')
			? '/setup'
			: page.url.pathname === '/acquisition'
				? '/acquisition'
				: page.url.pathname === '/debug'
					? '/debug'
					: '/'
	);

	function gotoView(id: Pathname) {
		goto(resolve(id), { keepFocus: true, noScroll: true });
	}

	function selectView(id: Pathname) {
		if (viewId === id) return;
		if (id === '/' && lastInstrumentPath && lastInstrumentPath !== '/') {
			goto(resolve(lastInstrumentPath as '/'), { keepFocus: true, noScroll: true });
		} else {
			gotoView(id);
		}
	}

	let closeDialogOpen = $state(false);
</script>

<div class="h-screen w-full text-fg">
	<PaneGroup direction="horizontal" autoSaveId="main-h">
		<Pane defaultSize={60} minSize={50} maxSize={70}>
			<div class="grid h-full grid-rows-[auto_1fr]">
				<header
					class="@container grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-3 border-b border-border bg-elevated px-4 py-4 @min-[800px]:grid-cols-[auto_auto_1fr]"
				>
					<!-- Logo + close-session dialog -->
					<div class="flex items-center">
						<AppMenu {app}>
							{#snippet trigger()}
								<VoxelLogo class="size-ui-sm" />
								<ChevronDown width="14" height="14" class="ml-1 text-fg-muted/60" />
							{/snippet}
							{#snippet extraItems()}
								<DropdownMenu.Item onclick={() => selectView('/debug')}>Debug</DropdownMenu.Item>
								<DropdownMenu.Item variant="destructive" onclick={() => (closeDialogOpen = true)}>
									<Power width="14" height="14" />
									Close Session
								</DropdownMenu.Item>
							{/snippet}
						</AppMenu>

						<Dialog.Root bind:open={closeDialogOpen}>
							<Dialog.Content size="sm" showCloseButton={false}>
								<Dialog.Header>
									<Dialog.Title>Close Session</Dialog.Title>
								</Dialog.Header>
								<p class="text-sm text-fg-muted">
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
					</div>

					<!-- Actions — explicitly pinned to row 1, last column -->
					<div class="col-start-2 row-start-1 flex items-center justify-end gap-4 @min-[800px]:col-start-3">
						<ProfileSelector {session} size="lg" class="min-w-64 flex-1" />
						<StartButton {session} />
					</div>

					<!-- Nav tabs — full-width row 2 at narrow, inline col 2 at wide -->
					<nav
						class="col-span-full flex gap-1 @min-[800px]:col-span-1 @min-[800px]:col-start-2 @min-[800px]:row-start-1 @min-[800px]:w-fit"
					>
						{#each navTabs as tab (tab.id)}
							{@const Icon = tab.icon}
							<button
								onclick={() => selectView(tab.id)}
								class={cn(
									'flex h-ui-md min-w-32 flex-1 items-center gap-2 rounded-md px-3 text-sm capitalize transition-colors',
									viewId === tab.id ? 'bg-element-selected text-fg shadow-sm' : 'text-fg-muted hover:text-fg'
								)}
								title={tab.label}
							>
								<Icon width="14" height="14" class="shrink-0" />
								{tab.label}
							</button>
						{/each}
					</nav>
				</header>
				{@render children()}
			</div>
		</Pane>

		<PaneDivider direction="vertical" />

		<!-- Right column: Viewer (Preview + Grid Canvas) -->
		<Pane defaultSize={45}>
			<main class="flex h-full flex-col overflow-hidden">
				<PaneGroup direction="vertical" autoSaveId="rightCol-v3">
					<Pane defaultSize={50} minSize={30} class="flex flex-1 flex-col justify-center">
						<PreviewCanvas previewer={session.preview} />
					</Pane>
					<PaneDivider direction="horizontal" />
					<Pane defaultSize={50} minSize={30} class="h-full flex-1">
						<GridCanvas {session} />
					</Pane>
				</PaneGroup>
			</main>
		</Pane>
	</PaneGroup>
</div>
