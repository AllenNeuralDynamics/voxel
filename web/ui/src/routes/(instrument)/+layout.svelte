<script lang="ts" module>
	/** Last visited path within the instrument route group. */
	export let lastInstrumentPath: string = '/';
</script>

<script lang="ts">
	import { getSessionContext, getLogsContext } from '$lib/context';
	import { cn, sanitizeString } from '$lib/utils';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { Collapsible } from 'bits-ui';
	import { ChevronDown, ChevronRight } from '$lib/icons';
	import { DropdownMenu } from '$lib/ui/kit';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import LogViewer from '$lib/ui/LogViewer.svelte';

	// Track the current instrument sub-path so we can restore it
	$effect(() => {
		lastInstrumentPath = page.url.pathname;
	});

	let { children } = $props();

	const session = getSessionContext();
	const { logs, clearLogs } = $derived(getLogsContext());
	const config = $derived(session.config);

	// --- Route-derived state ---

	const activeDeviceId = $derived(page.route.id === '/(instrument)/devices/[id]' ? page.params.id : undefined);
	const activeProfileId = $derived(page.route.id === '/(instrument)/profiles/[id]' ? page.params.id : undefined);
	const isChannelsActive = $derived(!activeDeviceId && !activeProfileId);

	function nav(path: string) {
		goto(resolve(path as '/'), { keepFocus: true, noScroll: true });
	}

	// --- Nav data (single source of truth for both layouts) ---

	interface NavItem {
		id: string;
		label: string;
		path: string;
		active: boolean;
	}

	interface ProfileNavItem extends NavItem {
		isActiveProfile: boolean;
	}

	interface DeviceNavItem extends NavItem {
		connected: boolean;
	}

	const profileItems: ProfileNavItem[] = $derived(
		Object.entries(config.profiles).map(([id, profile]) => ({
			id,
			label: profile.label ?? sanitizeString(id),
			path: `/profiles/${id}`,
			active: activeProfileId === id,
			isActiveProfile: id === session.activeProfileId
		}))
	);

	const deviceItems: DeviceNavItem[] = $derived(
		[...session.devices.devices].map(([id, device]) => ({
			id,
			label: sanitizeString(id),
			path: `/devices/${id}`,
			active: activeDeviceId === id,
			connected: device.connected
		}))
	);

	function activateAndNav(profileId: string) {
		session.activateProfile(profileId);
		nav(`/profiles/${profileId}`);
	}

	// --- Shared style helpers ---

	function navClass(active: boolean): string {
		return cn(
			'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm cursor-pointer transition-colors',
			active ? 'bg-element-selected text-fg' : 'text-fg-muted hover:bg-element-hover hover:text-fg'
		);
	}

	function triggerClass(active: boolean): string {
		return cn(
			'flex items-center gap-1 rounded-md px-2 py-1.5 text-sm cursor-pointer transition-colors',
			active ? 'bg-element-selected text-fg' : 'text-fg-muted hover:bg-element-hover hover:text-fg'
		);
	}

	function segmentClass(active: boolean): string {
		return cn(
			'flex flex-1 items-center gap-1.5 px-3 text-sm transition-colors h-ui-md cursor-pointer',
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

<!-- Shared snippets for profile badges (used by both layouts) -->
{#snippet profileBadge(item: { id: string; active: boolean; isActiveProfile: boolean }, reveal: 'always' | 'hover')}
	{#if item.isActiveProfile}
		<span class="shrink-0 rounded-full bg-success/15 px-1.5 py-px text-center text-xs font-medium text-success">
			Active
		</span>
	{:else}
		<span
			role="button"
			tabindex="0"
			class={cn(
				'shrink-0 rounded-full border border-fg-faint px-1.5 py-px text-center text-xs font-medium text-fg-muted transition-all hover:bg-element-hover hover:text-fg',
				reveal === 'always' || item.active
					? 'pointer-events-auto opacity-100'
					: 'pointer-events-none opacity-0 group-hover:pointer-events-auto group-hover:opacity-100 group-data-highlighted:pointer-events-auto group-data-highlighted:opacity-100'
			)}
			onclick={(e: MouseEvent) => {
				e.stopPropagation();
				activateAndNav(item.id);
			}}
			onkeydown={(e: KeyboardEvent) => {
				if (e.key === 'Enter') {
					e.stopPropagation();
					activateAndNav(item.id);
				}
			}}
		>
			Activate
		</span>
	{/if}
{/snippet}

{#snippet deviceDot(item: { connected: boolean })}
	<span
		class={cn('h-1.5 w-1.5 shrink-0 rounded-full', item.connected ? 'bg-success' : 'bg-fg-muted/30')}
		title={item.connected ? 'Connected' : 'Disconnected'}
	></span>
{/snippet}

<div class="@container flex h-full flex-col">
	<!-- ═══ Wide: sidebar + content row ═══ -->
	<div class="flex min-h-0 flex-1">
		<aside class="hidden w-56 shrink-0 flex-col border-r border-border bg-card py-3 @[960px]:flex">
			<div class="flex-1 space-y-2 overflow-auto">
				<!-- Channels -->
				<nav class="px-3">
					<button onclick={() => nav('/')} class={navClass(isChannelsActive)}>Channels</button>
				</nav>

				<!-- Profiles -->
				<nav class="mt-1 space-y-0.5 border-y border-border px-3 py-2">
					<p class="px-2 py-1 text-xs font-semibold tracking-wide text-fg-muted/60 uppercase">Profiles</p>
					{#each profileItems as item (item.id)}
						<button onclick={() => nav(item.path)} class="group {navClass(item.active)}">
							<span class="truncate">{item.label}</span>
							{@render profileBadge(item, 'hover')}
						</button>
					{/each}
				</nav>

				<!-- Devices -->
				<Collapsible.Root open>
					<Collapsible.Trigger class="group flex w-full items-center justify-between py-1 pr-4 pl-5">
						<p class="text-xs font-semibold tracking-wide text-fg-muted/60 uppercase">Devices</p>
						<ChevronRight
							width="12"
							height="12"
							class="shrink-0 text-fg-muted transition-transform group-data-[state=open]:rotate-90"
						/>
					</Collapsible.Trigger>
					<Collapsible.Content>
						<nav class="mt-1 space-y-0.5 px-3">
							{#each deviceItems as item (item.id)}
								<button onclick={() => nav(item.path)} class={navClass(item.active)}>
									<span class="truncate">{item.label}</span>
									{@render deviceDot(item)}
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
			<Pane class="h-full overflow-auto py-2">
				{@render children()}
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

	<!-- ═══ Narrow: segmented footer nav with dropdowns ═══ -->
	<nav class="flex h-ui-xl items-center gap-2 border-t border-border bg-card px-4 py-2 @[960px]:hidden">
		<div class="flex flex-1 divide-x divide-border overflow-hidden rounded-lg border border-border">
			<button onclick={() => nav('/')} class={segmentClass(isChannelsActive)}>Channels</button>

			<DropdownMenu.Root>
				{@const activeProfile = profileItems.find((p) => p.active)}
				<DropdownMenu.Trigger class={cn('justify-between', segmentClass(!!activeProfileId))}>
					{#if activeProfile}
						{activeProfile.label}
						{@render profileBadge(activeProfile, 'always')}
					{:else}
						Profiles
					{/if}
					<ChevronDown width="12" height="12" class="text-fg-muted" />
				</DropdownMenu.Trigger>
				<DropdownMenu.Content align="start" side="top" class="w-(--bits-dropdown-menu-trigger-width)">
					{#each profileItems as item (item.id)}
						<DropdownMenu.Item
							class="group flex w-full items-center justify-between gap-4"
							onclick={() => nav(item.path)}
						>
							<span class="truncate">{item.label}</span>
							{@render profileBadge(item, 'always')}
						</DropdownMenu.Item>
					{/each}
				</DropdownMenu.Content>
			</DropdownMenu.Root>

			<DropdownMenu.Root>
				{@const activeDevice = deviceItems.find((d) => d.active)}
				<DropdownMenu.Trigger class={cn('justify-between', segmentClass(!!activeDeviceId))}>
					{#if activeDevice}
						{activeDevice.label}
						{@render deviceDot(activeDevice)}
					{:else}
						Devices
					{/if}
					<ChevronDown width="12" height="12" class="text-fg-muted" />
				</DropdownMenu.Trigger>
				<DropdownMenu.Content align="start" side="top" class="w-(--bits-dropdown-menu-trigger-width)">
					{#each deviceItems as item (item.id)}
						<DropdownMenu.Item class="flex w-full items-center justify-between gap-4" onclick={() => nav(item.path)}>
							<span class="truncate">{item.label}</span>
							{@render deviceDot(item)}
						</DropdownMenu.Item>
					{/each}
				</DropdownMenu.Content>
			</DropdownMenu.Root>
		</div>

		<div class="flex overflow-hidden rounded-lg border border-border">
			<button onclick={toggleLogs} class={segmentClass(logsOpen)}>Logs</button>
		</div>
	</nav>
</div>
