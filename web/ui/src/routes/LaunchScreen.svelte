<script lang="ts">
	import type { App } from '$lib/main';
	import type { SessionDirectory, JsonSchema } from '$lib/main';
	import SessionForm from './SessionForm.svelte';
	import LogViewer from '$lib/ui/LogViewer.svelte';
	import { Collapsible, Tooltip } from 'bits-ui';
	import { ChevronRight, FolderOpenOutline, ArrowRight } from '$lib/icons';
	import VoxelLogo from '$lib/ui/VoxelLogo.svelte';

	const { app }: { app: App } = $props();

	let sessions = $state<SessionDirectory[]>([]);
	let loadingSessions = $state(false);
	let error = $state<string | null>(null);
	let metadataTargets = $state<Record<string, string>>({});
	let metadataSchema = $state<JsonSchema | null>(null);

	const roots = $derived(app.status?.roots ?? []);
	const rigs = $derived(app.status?.rigs ?? []);
	const phase = $derived(app.status?.phase);
	const isIdle = $derived(phase === 'idle');
	const isLaunching = $derived(phase === 'launching');
	const connectionState = $derived(app.client.connectionState);
	const connectionStatus = $derived.by(() => {
		switch (connectionState) {
			case 'connected':
				return { color: 'bg-success', text: 'Connected' };
			case 'connecting':
			case 'reconnecting':
				return { color: 'bg-warning', text: app.client.connectionMessage };
			case 'failed':
				return { color: 'bg-danger', text: app.client.connectionMessage };
			default:
				return { color: 'bg-muted-foreground', text: 'Offline' };
		}
	});
	const logs = $derived(app.logs);

	$effect(() => {
		if (roots.length > 0) {
			loadAllSessions();
		}
	});

	$effect(() => {
		app
			.fetchMetadataTargets()
			.then((targets) => {
				metadataTargets = targets;
			})
			.catch((e) => {
				console.warn('[LaunchScreen] Failed to fetch metadata targets:', e);
			});
	});

	async function loadAllSessions() {
		loadingSessions = true;
		error = null;
		try {
			const allSessions = await Promise.all(roots.map((root) => app.fetchSessions(root.name)));
			sessions = allSessions.flat().sort((a, b) => new Date(b.modified).getTime() - new Date(a.modified).getTime());
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load sessions';
			sessions = [];
		} finally {
			loadingSessions = false;
		}
	}

	async function handleMetadataTargetChanged(target: string) {
		try {
			metadataSchema = await app.fetchMetadataSchema(target);
		} catch (e) {
			console.warn('[LaunchScreen] Failed to fetch metadata schema:', e);
			metadataSchema = null;
		}
	}

	async function handleLaunchSession(
		rootName: string,
		rigConfig: string,
		sessionName: string,
		metadataTarget: string,
		metadata: Record<string, unknown>
	) {
		error = null;
		try {
			await app.createSession(rootName, rigConfig, sessionName, metadataTarget, metadata);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create session';
		}
	}

	async function handleResumeSession(session: SessionDirectory) {
		error = null;
		try {
			await app.resumeSession(session.path);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to resume session';
		}
	}

	function formatRelativeTime(isoString: string): string {
		const date = new Date(isoString);
		const now = new Date();
		const diffMs = now.getTime() - date.getTime();
		const diffMins = Math.floor(diffMs / 60000);
		const diffHours = Math.floor(diffMs / 3600000);
		const diffDays = Math.floor(diffMs / 86400000);

		if (diffMins < 1) return 'Just now';
		if (diffMins < 60) return `${diffMins}m ago`;
		if (diffHours < 24) return `${diffHours}h ago`;
		if (diffDays < 7) return `${diffDays}d ago`;

		return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
	}
</script>

<div class="flex h-screen w-full bg-background">
	<div class="flex w-150 shrink-0 flex-col border-r border-border">
		<div class="shrink-0 p-4 pb-0">
			<div class="mb-6 flex flex-col gap-1">
				<div class="flex items-center gap-2">
					<VoxelLogo
						class="h-8 w-8"
						topLeft={{ top: '#2EF58D', left: '#22CC75', right: '#189960' }}
						topRight={{ top: '#F52E64', left: '#CC2250', right: '#99193C' }}
						bottom={{ top: '#F5D62E', left: '#CCB222', right: '#998619' }}
					/>
					<h1 class="text-2xl font-light text-foreground uppercase">Voxel</h1>
				</div>
				<p class="text-xs text-muted-foreground">Light sheet microscopy</p>
			</div>

			{#if error}
				<div class="mb-6 rounded border border-danger/50 bg-danger/10 px-4 py-3 text-sm text-danger">
					{error}
				</div>
			{/if}
		</div>

		{#if connectionState === 'failed'}
			<div class="flex flex-1 flex-col items-center justify-center gap-3">
				<p class="text-sm text-danger">{app.client.connectionMessage}</p>
				<button
					onclick={() => app.retryConnection()}
					class="rounded border border-input bg-transparent px-4 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
				>
					Retry
				</button>
			</div>
		{:else if !isIdle || isLaunching}
			<div class="flex flex-1 items-center justify-center gap-2">
				<div class="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-border border-t-primary"></div>
				<p class="text-xs text-muted-foreground">
					{isLaunching ? 'Starting session...' : app.client.connectionMessage}
				</p>
			</div>
		{:else}
			<div class="shrink-0 px-4">
				<Collapsible.Root class="mb-6">
					<Collapsible.Trigger
						class="flex w-full items-center justify-between py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground/80 [&[data-state=open]>svg]:rotate-90"
					>
						New Session
						<ChevronRight width="16" height="16" class="transition-transform duration-200" />
					</Collapsible.Trigger>
					<Collapsible.Content
						class="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down"
					>
						<SessionForm
							{roots}
							{rigs}
							{metadataTargets}
							{metadataSchema}
							onMetadataTargetChanged={handleMetadataTargetChanged}
							onSubmit={handleLaunchSession}
						/>
					</Collapsible.Content>
				</Collapsible.Root>
			</div>

			<div class="px-4">
				<h2 class="text-sm font-medium text-muted-foreground">Recent Sessions</h2>
			</div>
			<div class="min-h-0 flex-1 overflow-y-auto px-4 pt-2">
				{#if loadingSessions}
					<div class="flex items-center justify-center rounded border border-border bg-card py-12">
						<div class="h-5 w-5 animate-spin rounded-full border-2 border-border border-t-muted-foreground"></div>
						<span class="ml-3 text-sm text-muted-foreground">Loading sessions...</span>
					</div>
				{:else if sessions.length === 0}
					<div
						class="flex flex-col items-center justify-center rounded border border-dashed border-border bg-card py-10"
					>
						<FolderOpenOutline width="32" height="32" class="text-muted-foreground/50" />
						<p class="mt-2 text-sm text-muted-foreground">No recent sessions</p>
						<p class="text-xs text-muted-foreground/60">Create a new session to get started</p>
					</div>
				{:else}
					<div class="space-y-2">
						{#each sessions as session (session.path)}
							<button
								class="group flex w-full items-center gap-3 rounded border border-border bg-card px-3 py-2.5 text-left transition-colors hover:border-foreground/20 hover:bg-accent"
								onclick={() => handleResumeSession(session)}
							>
								<span class="min-w-0 flex-1 truncate text-xs text-foreground">
									<span class="text-muted-foreground">{session.root_name} /</span>
									{session.name}
								</span>
								<span class="shrink-0 text-[0.65rem] text-muted-foreground/60">
									{formatRelativeTime(session.modified)}
								</span>
								<ArrowRight
									width="14"
									height="14"
									class="shrink-0 text-muted-foreground/30 transition-colors group-hover:text-foreground"
								/>
							</button>
						{/each}
					</div>
				{/if}
			</div>
		{/if}

		<div class="shrink-0 p-4 pt-2">
			<Tooltip.Provider>
				<Tooltip.Root delayDuration={200}>
					<Tooltip.Trigger class="cursor-pointer">
						<span class="block h-1.5 w-1.5 rounded-full {connectionStatus.color}"></span>
					</Tooltip.Trigger>
					<Tooltip.Portal>
						<Tooltip.Content
							sideOffset={4}
							class="z-50 rounded border bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md"
						>
							{connectionStatus.text}
						</Tooltip.Content>
					</Tooltip.Portal>
				</Tooltip.Root>
			</Tooltip.Provider>
		</div>
	</div>

	<div class="flex flex-1 flex-col bg-card p-4">
		<LogViewer {logs} onClear={() => app.clearLogs()} />
	</div>
</div>
