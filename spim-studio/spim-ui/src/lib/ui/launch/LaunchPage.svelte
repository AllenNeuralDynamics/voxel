<script lang="ts">
	import type { App } from '$lib/app';
	import type { SessionDirectory } from '$lib/core';
	import SessionList from './SessionList.svelte';
	import NewSessionForm from './NewSessionForm.svelte';
	import LogViewer from '$lib/ui/LogViewer.svelte';
	import ClientStatus from '$lib/ui/ClientStatus.svelte';

	const { app }: { app: App } = $props();

	// State
	let sessions = $state<SessionDirectory[]>([]);
	let loadingSessions = $state(false);
	let error = $state<string | null>(null);

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

	async function handleLaunchSession(rootName: string, sessionName: string, rigConfig?: string) {
		error = null;
		try {
			await app.launchSession(rootName, sessionName, rigConfig);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to launch session';
		}
	}

	async function handleResumeSession(session: SessionDirectory) {
		error = null;
		try {
			await app.launchSession(session.root_name, session.name);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to resume session';
		}
	}
</script>

<div class="flex h-screen w-full bg-zinc-950">
	<!-- Main content panel -->
	<div class="flex w-2/5 flex-col overflow-y-auto p-8">
		<!-- Header -->
		<div class="mb-6">
			{#if isLaunching}
				<div class="flex items-center gap-4">
					<div class="h-8 w-8 animate-spin rounded-full border-4 border-zinc-700 border-t-blue-500"></div>
					<div>
						<h1 class="text-xl font-semibold text-zinc-100">Starting Session</h1>
						<p class="text-sm text-zinc-400">Initializing rig and devices...</p>
					</div>
				</div>
			{:else}
				<h1 class="text-2xl font-semibold text-zinc-100">SPIM Studio</h1>
				<p class="mt-1 text-sm text-zinc-400">Select or create a session to get started</p>
			{/if}
		</div>

		<!-- Error display -->
		{#if error}
			<div class="mb-6 rounded border border-rose-500/50 bg-rose-500/10 px-4 py-3 text-sm text-rose-400">
				{error}
			</div>
		{/if}

		{#if !isLaunching}
			<!-- New session form -->
			<div class="mb-6 space-y-2">
				<h2 class="text-sm font-medium text-zinc-300">New Session</h2>
				<NewSessionForm {roots} {rigs} onLaunch={handleLaunchSession} />
			</div>

			<!-- Recent sessions from all roots -->
			<div class="space-y-2">
				<h2 class="text-sm font-medium text-zinc-300">Recent Sessions</h2>
				<SessionList {sessions} loading={loadingSessions} onResume={handleResumeSession} />
			</div>
		{/if}

		<!-- Connection status (pushed to bottom) -->
		<div class="mt-auto pt-4">
			<ClientStatus client={app.client} />
		</div>
	</div>

	<!-- Log viewer panel (always visible) -->
	<div class="flex w-3/5 flex-col border-l border-zinc-700 bg-zinc-900 p-4">
		<LogViewer {logs} onClear={() => app.clearLogs()} />
	</div>
</div>
