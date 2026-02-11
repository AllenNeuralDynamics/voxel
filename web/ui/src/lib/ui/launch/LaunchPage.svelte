<script lang="ts">
	import type { App } from '$lib/app';
	import type { SessionDirectory, JsonSchema } from '$lib/core';
	import SessionList from './SessionList.svelte';
	import SessionForm from './SessionForm.svelte';
	import LogViewer from '$lib/ui/LogViewer.svelte';
	import ClientStatus from '$lib/ui/ClientStatus.svelte';
	import { Collapsible } from 'bits-ui';
	import Icon from '@iconify/svelte';

	const { app }: { app: App } = $props();

	// State
	let sessions = $state<SessionDirectory[]>([]);
	let loadingSessions = $state(false);
	let error = $state<string | null>(null);
	let metadataTargets = $state<Record<string, string>>({});
	let metadataSchema = $state<JsonSchema | null>(null);

	// Derived
	const roots = $derived(app.status?.roots ?? []);
	const rigs = $derived(app.status?.rigs ?? []);
	const isLaunching = $derived(app.status?.phase === 'launching');
	const logs = $derived(app.logs);

	// Load sessions from ALL roots when roots change
	$effect(() => {
		if (roots.length > 0) {
			loadAllSessions();
		}
	});

	// Fetch metadata targets on mount
	$effect(() => {
		app
			.fetchMetadataTargets()
			.then((targets) => {
				metadataTargets = targets;
			})
			.catch((e) => {
				console.warn('[LaunchPage] Failed to fetch metadata targets:', e);
			});
	});

	async function loadAllSessions() {
		loadingSessions = true;
		error = null;
		try {
			// Fetch sessions from all roots in parallel
			const allSessions = await Promise.all(roots.map((root) => app.fetchSessions(root.name)));
			// Flatten and sort by modified date (newest first)
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
			console.warn('[LaunchPage] Failed to fetch metadata schema:', e);
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
	<!-- Sidebar -->
	<div class="flex w-[600px] shrink-0 flex-col overflow-y-auto border-r border-border p-4">
		<!-- Header -->
		<div class="mb-6 flex flex-col gap-4">
			<div class="flex items-center gap-3">
				<img src="/voxel-logo.png" alt="Voxel" class="h-10 w-10" />
				<div>
					<h1 class="text-2xl font-semibold text-foreground">Voxel</h1>
					<p class="text-sm text-muted-foreground">Light sheet microscope control</p>
				</div>
			</div>

			{#if isLaunching}
				<div class="flex items-center gap-2">
					<div class="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-primary"></div>
					<p class="text-sm text-muted-foreground">Starting session...</p>
				</div>
			{/if}
		</div>

		<!-- Error display -->
		{#if error}
			<div class="mb-6 rounded border border-danger/50 bg-danger/10 px-4 py-3 text-sm text-danger">
				{error}
			</div>
		{/if}

		{#if !isLaunching}
			<Collapsible.Root class="mb-6">
				<Collapsible.Trigger
					class="flex w-full items-center justify-between py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground/80 [&[data-state=open]>svg]:rotate-90"
				>
					New Session
					<Icon icon="mdi:chevron-right" width="16" height="16" class="transition-transform duration-200" />
				</Collapsible.Trigger>
				<Collapsible.Content class="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
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

			<!-- Recent sessions from all roots -->
			<div class="space-y-2">
				<h2 class="text-sm font-medium text-muted-foreground">Recent Sessions</h2>
				<SessionList {sessions} loading={loadingSessions} onResume={handleResumeSession} />
			</div>
		{/if}

		<!-- Connection status (pushed to bottom) -->
		<div class="mt-auto pt-4">
			<ClientStatus client={app.client} />
		</div>
	</div>

	<!-- Log viewer -->
	<div class="flex flex-1 flex-col bg-card p-4">
		<LogViewer {logs} onClear={() => app.clearLogs()} />
	</div>
</div>
