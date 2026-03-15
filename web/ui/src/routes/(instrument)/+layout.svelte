<script lang="ts">
	import { getSessionContext, getLogsContext } from '$lib/context';
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

	const session = getSessionContext();
	const { logs, clearLogs } = $derived(getLogsContext());
	const config = $derived(session.config);

	// --- Sidebar nav (driven by routes) ---

	const activeDeviceId = $derived(page.route.id === '/(instrument)/devices/[id]' ? page.params.id : undefined);

	const activeProfileId = $derived(page.route.id === '/(instrument)/profiles/[id]' ? page.params.id : undefined);

	const isChannelsActive = $derived(!activeDeviceId && !activeProfileId);

	function nav(path: string) {
		goto(resolve(path as '/'), { keepFocus: true, noScroll: true });
	}

	function navClass(active: boolean): string {
		return cn(
			'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm cursor-pointer transition-colors',
			active ? 'bg-element-selected text-fg' : 'text-fg-muted hover:bg-element-hover hover:text-fg'
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
		<div class="flex-1 space-y-2 overflow-auto">
			<!-- Channels -->
			<nav class="px-3">
				<button onclick={() => nav('/')} class={navClass(isChannelsActive)}> Channels </button>
			</nav>

			<!-- Profiles -->
			<nav class="mt-1 space-y-0.5 border-y border-border px-3 py-2">
				<p class="text-fg-muted/60 px-2 py-1 text-xs font-semibold tracking-wide uppercase">Profiles</p>
				{#each Object.entries(config.profiles) as [id, profile] (id)}
					{@const isActiveProfile = id === session.activeProfileId}
					{@const isViewed = activeProfileId === id}
					<button onclick={() => nav(`/profiles/${id}`)} class="group {navClass(isViewed)}">
						<span class="truncate">{profile.label ?? sanitizeString(id)}</span>
						{#if isActiveProfile}
							<span
								class="w-13 shrink-0 rounded-full bg-success/15 py-0.5 text-center text-xs font-medium text-success"
							>
								Active
							</span>
						{:else}
							<span
								role="button"
								tabindex="0"
								class={cn(
									'w-13 shrink-0 rounded-full border py-0.5 text-center text-xs font-medium transition-all',
									isViewed
										? 'pointer-events-auto border-warning/40 bg-warning/10 text-warning opacity-100 hover:bg-warning/20'
										: 'text-fg-muted hover:bg-element-hover hover:text-fg pointer-events-none border-border opacity-0 group-hover:pointer-events-auto group-hover:opacity-100'
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

			<!-- Devices -->
			<Collapsible.Root open>
				<Collapsible.Trigger class="group flex w-full items-center justify-between px-5 py-1">
					<p class="text-fg-muted/60 text-xs font-semibold tracking-wide uppercase">Devices</p>
					<ChevronRight
						width="12"
						height="12"
						class="text-fg-muted shrink-0 transition-transform group-data-[state=open]:rotate-90"
					/>
				</Collapsible.Trigger>
				<Collapsible.Content>
					<nav class="mt-1 space-y-0.5 px-3">
						{#each [...session.devices.devices] as [id, device] (id)}
							<button onclick={() => nav(`/devices/${id}`)} class={navClass(activeDeviceId === id)}>
								<span class="truncate">{sanitizeString(id)}</span>
								<span
									class={cn('h-1.5 w-1.5 shrink-0 rounded-full', device.connected ? 'bg-success' : 'bg-fg-muted/30')}
									title={device.connected ? 'Connected' : 'Disconnected'}
								></span>
							</button>
						{/each}
					</nav>
				</Collapsible.Content>
			</Collapsible.Root>
		</div>

		<!-- Logs pinned to bottom -->
		<div class="space-y-0.5 border-t border-border px-3 pt-3">
			<button
				onclick={toggleLogs}
				class={cn(
					'flex w-full cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-sm transition-colors',
					logsOpen ? 'bg-element-selected text-fg' : 'text-fg-muted hover:bg-element-hover hover:text-fg'
				)}
			>
				Logs
			</button>
		</div>
	</aside>

	<!-- Main Content -->
	<PaneGroup direction="vertical" autoSaveId="instrument-v" class="flex-1">
		<Pane>
			<div class="h-full overflow-auto px-4 py-2">
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
				<LogViewer {logs} onClear={clearLogs} />
			</div>
		</Pane>
	</PaneGroup>
</div>
