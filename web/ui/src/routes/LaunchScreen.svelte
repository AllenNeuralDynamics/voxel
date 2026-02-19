<script lang="ts">
	import type { App } from '$lib/main';
	import type { SessionDirectory, JsonSchema } from '$lib/main';
	import SessionList from '$lib/ui/launch/SessionList.svelte';
	import SessionForm from '$lib/ui/launch/SessionForm.svelte';
	import LogViewer from '$lib/ui/LogViewer.svelte';
	import ClientStatus from '$lib/ui/ClientStatus.svelte';
	import { Collapsible } from 'bits-ui';
	import Icon from '@iconify/svelte';
	import VoxelLogo from '$lib/ui/VoxelLogo.svelte';

	const { app }: { app: App } = $props();

	let sessions = $state<SessionDirectory[]>([]);
	let loadingSessions = $state(false);
	let error = $state<string | null>(null);
	let metadataTargets = $state<Record<string, string>>({});
	let metadataSchema = $state<JsonSchema | null>(null);

	const roots = $derived(app.status?.roots ?? []);
	const rigs = $derived(app.status?.rigs ?? []);
	const isLaunching = $derived(app.status?.phase === 'launching');
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

				{#if isLaunching}
					<div class="flex items-center gap-2">
						<div class="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-primary"></div>
						<p class="text-sm text-muted-foreground">Starting session...</p>
					</div>
				{/if}
			</div>

			{#if error}
				<div class="mb-6 rounded border border-danger/50 bg-danger/10 px-4 py-3 text-sm text-danger">
					{error}
				</div>
			{/if}
		</div>

		{#if !isLaunching}
			<div class="shrink-0 px-4">
				<Collapsible.Root class="mb-6">
					<Collapsible.Trigger
						class="flex w-full items-center justify-between py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground/80 [&[data-state=open]>svg]:rotate-90"
					>
						New Session
						<Icon icon="mdi:chevron-right" width="16" height="16" class="transition-transform duration-200" />
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
				<SessionList {sessions} loading={loadingSessions} onResume={handleResumeSession} />
			</div>
		{/if}

		<div class="shrink-0 p-4 pt-2">
			<ClientStatus client={app.client} />
		</div>
	</div>

	<div class="flex flex-1 flex-col bg-card p-4">
		<LogViewer {logs} onClear={() => app.clearLogs()} />
	</div>
</div>
