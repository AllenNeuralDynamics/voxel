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
	import { ChevronDown, ClipboardCheckOutline, LayersOutline, Microscope, Power } from '$lib/icons';
	import AppMenu from './AppMenu.svelte';
	import VoxelLogo from '$lib/ui/VoxelLogo.svelte';
	import StartButton from '$lib/ui/StartButton.svelte';
	import { ProfileSelector } from '$lib/ui/profile';
	import { cn } from '$lib/utils';
	import type { Pathname } from '$app/types';

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
		{ id: '/setup', label: 'Setup', icon: ClipboardCheckOutline },
		{ id: '/acquisition', label: 'Acquisition', icon: LayersOutline }
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
		if (viewId !== id) gotoView(id);
	}

	let closeDialogOpen = $state(false);
</script>

<div class="text-fg h-screen w-full">
	<PaneGroup direction="horizontal" autoSaveId="main-h">
		<Pane defaultSize={60} minSize={50} maxSize={70}>
			<div class="grid h-full grid-rows-[auto_1fr]">
				<header
					class="bg-elevated @container grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-3 border-b border-border px-4 py-4 @min-[800px]:grid-cols-[auto_auto_1fr]"
				>
					<!-- Logo + close-session dialog -->
					<div class="flex items-center">
						<AppMenu {app}>
							{#snippet trigger()}
								<VoxelLogo class="size-ui-sm" />
								<ChevronDown width="14" height="14" class="text-fg-muted/60 ml-1" />
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
					</div>

					<!-- Actions — explicitly pinned to row 1, last column -->
					<div class="col-start-2 row-start-1 flex items-center justify-end gap-4 @min-[800px]:col-start-3">
						<ProfileSelector {session} size="lg" class="min-w-64 flex-1" />
						<StartButton {session} />
					</div>

					<!-- Nav tabs — full-width row 2 at narrow, inline col 2 at wide -->
					<nav
						class="col-span-full flex *:flex-1 @min-[800px]:col-span-1 @min-[800px]:col-start-2 @min-[800px]:row-start-1 @min-[800px]:w-fit"
					>
						{#each navTabs as tab (tab.id)}
							{@const Icon = tab.icon}
							<button
								onclick={() => selectView(tab.id)}
								class={cn(
									'h-ui-lg border-fg-faint -ml-px flex min-w-28 items-center justify-center gap-1.5 border px-3 text-base capitalize first:ml-0 first:rounded-l last:rounded-r',
									viewId === tab.id ? 'text-fg bg-element-bg' : 'text-fg-muted bg-elevated hover:bg-element-hover/50'
								)}
								title={tab.label}
							>
								<Icon width="18" height="18" />
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
