<script lang="ts">
	import { getAppContext } from '$lib/context';
	import { useSearchParams, createSearchParamsSchema } from 'runed/kit';
	import { cn, sanitizeString } from '$lib/utils';
	import { Collapsible } from 'bits-ui';
	import { ChevronRight } from '$lib/icons';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import LogViewer from '$lib/ui/LogViewer.svelte';

	let { children } = $props();

	const app = getAppContext();
	const session = $derived(app.session!);
	const config = $derived(session.config);

	// --- Sidebar nav state (driven by URL search params) ---

	const params = useSearchParams(
		createSearchParamsSchema({
			nav: { type: 'string', default: 'channels' },
			id: { type: 'string', default: '' }
		}),
		{ pushHistory: false, noScroll: true }
	);

	type NavTarget = { type: 'device'; id: string } | { type: 'channels' } | { type: 'profile'; id: string };

	const activeNav = $derived<NavTarget>(
		params.nav === 'device' && params.id
			? { type: 'device', id: params.id }
			: params.nav === 'profile' && params.id
				? { type: 'profile', id: params.id }
				: { type: 'channels' }
	);

	function setNav(nav: NavTarget) {
		if (nav.type === 'channels') {
			params.nav = 'channels';
			params.id = '';
		} else {
			params.nav = nav.type;
			params.id = nav.id;
		}
	}

	function isActive(target: NavTarget): boolean {
		if (activeNav.type !== target.type) return false;
		if (target.type === 'device' && activeNav.type === 'device') return activeNav.id === target.id;
		if (target.type === 'profile' && activeNav.type === 'profile') return activeNav.id === target.id;
		return true;
	}

	function navClass(target: NavTarget): string {
		return cn(
			'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-xs cursor-pointer transition-colors',
			isActive(target)
				? 'bg-accent text-accent-foreground'
				: 'text-muted-foreground hover:bg-muted hover:text-foreground'
		);
	}

	// --- Log pane ---

	let logPane: Pane | undefined = $state(undefined);
	let logsOpen = $state(false);

	function toggleLogs() {
		if (logsOpen) {
			logPane?.collapse();
			logsOpen = false;
		} else {
			logPane?.expand();
			logsOpen = true;
		}
	}

	// --- Validate nav targets ---

	$effect(() => {
		if (activeNav.type === 'device') {
			const devices = session.devices.devices;
			if (!devices.has(activeNav.id)) {
				const firstId = [...devices.keys()][0];
				setNav(firstId ? { type: 'device', id: firstId } : { type: 'channels' });
			}
		} else if (activeNav.type === 'profile' && !(activeNav.id in session.config.profiles)) {
			setNav({ type: 'channels' });
		}
	});
</script>

<div class="flex h-full">
	<!-- Sidebar Navigation -->
	<aside class="flex w-56 shrink-0 flex-col border-r border-border bg-card py-3">
		<div class="flex-1 space-y-4 overflow-auto">
			<!-- Channels -->
			<nav class="space-y-0.5 px-3">
				<button onclick={() => setNav({ type: 'channels' })} class={navClass({ type: 'channels' })}> Channels </button>
			</nav>

			<!-- Profiles -->
			<Collapsible.Root open>
				<Collapsible.Trigger class="group flex w-full items-center justify-between px-5 py-1">
					<span class="text-[0.5rem] font-medium tracking-wide text-muted-foreground uppercase"> Profiles </span>
					<ChevronRight
						width="12"
						height="12"
						class="shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90"
					/>
				</Collapsible.Trigger>
				<Collapsible.Content>
					<nav class="mt-1 space-y-0.5 px-3">
						{#each Object.entries(config.profiles) as [id, profile] (id)}
							{@const isActiveProfile = id === session.activeProfileId}
							{@const isViewed = activeNav.type === 'profile' && activeNav.id === id}
							<button onclick={() => setNav({ type: 'profile', id })} class="group {navClass({ type: 'profile', id })}">
								<span class="truncate">{profile.label ?? sanitizeString(id)}</span>
								{#if isActiveProfile}
									<span
										class="w-13 shrink-0 rounded-full bg-success/15 py-0.5 text-center text-[0.5rem] font-medium text-success"
									>
										Active
									</span>
								{:else}
									<span
										role="button"
										tabindex="0"
										class={cn(
											'w-13 shrink-0 rounded-full border py-0.5 text-center text-[0.5rem] font-medium transition-all',
											isViewed
												? 'pointer-events-auto border-amber-500/40 bg-amber-500/10 text-amber-500 opacity-100 hover:bg-amber-500/20'
												: 'pointer-events-none border-border text-muted-foreground opacity-0 group-hover:pointer-events-auto group-hover:opacity-100 hover:bg-muted hover:text-foreground'
										)}
										onclick={(e: MouseEvent) => {
											e.stopPropagation();
											session.activateProfile(id);
											setNav({ type: 'profile', id });
										}}
										onkeydown={(e: KeyboardEvent) => {
											if (e.key === 'Enter') {
												e.stopPropagation();
												session.activateProfile(id);
												setNav({ type: 'profile', id });
											}
										}}
									>
										Activate
									</span>
								{/if}
							</button>
						{/each}
					</nav>
				</Collapsible.Content>
			</Collapsible.Root>

			<!-- Devices -->
			<Collapsible.Root open>
				<Collapsible.Trigger class="group flex w-full items-center justify-between px-5 py-1">
					<span class="text-[0.5rem] font-medium tracking-wide text-muted-foreground uppercase"> Devices </span>
					<ChevronRight
						width="12"
						height="12"
						class="shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90"
					/>
				</Collapsible.Trigger>
				<Collapsible.Content>
					<nav class="mt-1 space-y-0.5 px-3">
						{#each [...session.devices.devices] as [id, device] (id)}
							<button onclick={() => setNav({ type: 'device', id })} class={navClass({ type: 'device', id })}>
								<span class="truncate">{sanitizeString(id)}</span>
								<span
									class={cn(
										'h-1.5 w-1.5 shrink-0 rounded-full',
										device.connected ? 'bg-success' : 'bg-muted-foreground/30'
									)}
									title={device.connected ? 'Connected' : 'Disconnected'}
								></span>
							</button>
						{/each}
					</nav>
				</Collapsible.Content>
			</Collapsible.Root>
		</div>

		<!-- Logs trigger pinned to bottom -->
		<div class="border-t border-border px-3 pt-3">
			<button
				onclick={toggleLogs}
				class={cn(
					'flex w-full cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-xs transition-colors',
					logsOpen ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
				)}
			>
				Logs
			</button>
		</div>
	</aside>

	<!-- Main Content -->
	<PaneGroup direction="vertical" autoSaveId="configure-v" class="flex-1">
		<Pane>
			<div class="h-full overflow-auto p-6">
				{@render children()}
			</div>
		</Pane>
		<PaneDivider direction="horizontal" />
		<Pane
			bind:this={logPane}
			collapsible
			collapsedSize={0}
			defaultSize={0}
			minSize={20}
			maxSize={50}
			onCollapse={() => {}}
		>
			<div class="h-full overflow-hidden bg-card p-2">
				<LogViewer logs={app.logs} onClear={() => app.clearLogs()} />
			</div>
		</Pane>
	</PaneGroup>
</div>
