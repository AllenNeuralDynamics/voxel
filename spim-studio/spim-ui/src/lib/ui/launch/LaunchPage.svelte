<script lang="ts">
	import type { App } from '$lib/app';
	import type { SessionDirectory } from '$lib/core';
	import SessionList from './SessionList.svelte';
	import NewSessionForm from './NewSessionForm.svelte';
	import LogViewer from './LogViewer.svelte';

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

<div class="flex h-full w-full bg-zinc-950">
	<!-- Main content panel -->
	<div class="flex flex-1 items-center justify-center p-8" class:max-w-xl={isLaunching}>
		<div class="w-full max-w-2xl space-y-6">
			<!-- Header -->
			<div class="text-center">
				{#if isLaunching}
					<div class="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-zinc-700 border-t-blue-500"></div>
					<h1 class="mt-4 text-xl font-semibold text-zinc-100">Starting Session</h1>
					<p class="mt-1 text-sm text-zinc-400">Initializing rig and devices...</p>
				{:else}
					<h1 class="text-2xl font-semibold text-zinc-100">SPIM Studio</h1>
					<p class="mt-1 text-sm text-zinc-400">Select or create a session to get started</p>
				{/if}
			</div>

			<!-- Error display -->
			{#if error}
				<div class="rounded border border-rose-500/50 bg-rose-500/10 px-4 py-3 text-sm text-rose-400">
					{error}
				</div>
			{/if}

			{#if !isLaunching}
				<!-- Recent sessions from all roots -->
				<div class="space-y-2">
					<h2 class="text-sm font-medium text-zinc-300">Recent Sessions</h2>
					<SessionList {sessions} loading={loadingSessions} onResume={handleResumeSession} />
				</div>

				<!-- New session form (includes root selector) -->
				<div class="space-y-2">
					<h2 class="text-sm font-medium text-zinc-300">New Session</h2>
					<NewSessionForm {roots} {rigs} onLaunch={handleLaunchSession} />
				</div>
			{/if}
		</div>
	</div>

	<!-- Log viewer sidebar (shown when launching) -->
	{#if isLaunching}
		<div class="flex w-125 flex-col border-l border-zinc-800 p-4">
			<h2 class="mb-2 text-sm font-medium text-zinc-300">Startup Log</h2>
			<LogViewer {logs} />
		</div>
	{/if}
</div>
