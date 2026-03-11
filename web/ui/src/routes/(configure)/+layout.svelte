<script lang="ts">
	import { getAppContext } from '$lib/context';
	import { cn, sanitizeString } from '$lib/utils';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { Collapsible } from 'bits-ui';
	import { ChevronRight } from '$lib/icons';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import LogViewer from '$lib/ui/LogViewer.svelte';

	let { children } = $props();

	const app = getAppContext();
	const session = $derived(app.session!);
	const config = $derived(session.config);

	// --- Sidebar nav (driven by routes) ---

	const activeDeviceId = $derived(page.route.id === '/(configure)/devices/[id]' ? page.params.id : undefined);

	const activeProfileId = $derived(page.route.id === '/(configure)/profiles/[id]' ? page.params.id : undefined);

	const isChannelsActive = $derived(!activeDeviceId && !activeProfileId);

	function nav(path: string) {
		goto(resolve(path as '/'), { keepFocus: true, noScroll: true });
	}

	function navClass(active: boolean): string {
		return cn(
			'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-xs cursor-pointer transition-colors',
			active ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
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
		if (activeDeviceId && !session.devices.devices.has(activeDeviceId)) {
			nav('/');
		} else if (activeProfileId && !(activeProfileId in session.config.profiles)) {
			nav('/');
		}
	});
</script>

<div class="flex h-full">
	<!-- Sidebar Navigation -->
	<aside class="flex w-56 shrink-0 flex-col border-r border-border bg-card py-3">
		<div class="flex-1 space-y-4 overflow-auto">
			<!-- Channels -->
			<nav class="space-y-0.5 px-3">
				<button onclick={() => nav('/')} class={navClass(isChannelsActive)}> Channels </button>
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
							{@const isViewed = activeProfileId === id}
							<button onclick={() => nav(`/profiles/${id}`)} class="group {navClass(isViewed)}">
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
											nav(`/profiles/${id}`);
										}}
										onkeydown={(e: KeyboardEvent) => {
											if (e.key === 'Enter') {
												e.stopPropagation();
												session.activateProfile(id);
												nav(`/profiles/${id}`);
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
							<button onclick={() => nav(`/devices/${id}`)} class={navClass(activeDeviceId === id)}>
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
