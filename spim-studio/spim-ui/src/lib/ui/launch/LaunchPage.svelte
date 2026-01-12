<script lang="ts">
	import type { App } from '$lib/app';
	import type { SessionRoot, SessionDirectory } from '$lib/core';
	import SessionList from './SessionList.svelte';
	import NewSessionForm from './NewSessionForm.svelte';
	import LogViewer from './LogViewer.svelte';

	const { app }: { app: App } = $props();

	// State
	let selectedRoot = $state<SessionRoot | null>(null);
	let sessions = $state<SessionDirectory[]>([]);
	let loadingSessions = $state(false);
	let error = $state<string | null>(null);

	// Derived
	const roots = $derived(app.status?.roots ?? []);
	const rigs = $derived(app.status?.rigs ?? []);
	const isLaunching = $derived(app.status?.phase === 'launching');
	const logs = $derived(app.logs);

	// Auto-select first root when available
	$effect(() => {
		if (!selectedRoot && roots.length > 0) {
			selectedRoot = roots[0];
		}
	});

	// Load sessions when root changes
	$effect(() => {
		if (selectedRoot) {
			loadSessions(selectedRoot.name);
		}
	});

	async function loadSessions(rootName: string) {
		loadingSessions = true;
		error = null;
		try {
			sessions = await app.fetchSessions(rootName);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load sessions';
			sessions = [];
		} finally {
			loadingSessions = false;
		}
	}

	async function handleLaunchSession(sessionName: string, rigConfig?: string) {
		if (!selectedRoot) return;
		error = null;
		try {
			await app.launchSession(selectedRoot.name, sessionName, rigConfig);
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

<div class="flex h-full w-full items-center justify-center bg-zinc-950 p-8">
	<div class="w-full max-w-2xl space-y-6">
		<!-- Header -->
		<div class="text-center">
			{#if isLaunching}
				<div
					class="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-zinc-700 border-t-blue-500"
				></div>
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

		<!-- Loading: show log viewer -->
		{#if isLaunching}
			<div class="space-y-2">
				<h2 class="text-sm font-medium text-zinc-300">Startup Log</h2>
				<LogViewer {logs} />
			</div>
		{:else}
			<!-- Root selector -->
			<div class="space-y-2">
				<label for="root-select" class="block text-sm font-medium text-zinc-300">Session Root</label>
				<select
					id="root-select"
					class="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-zinc-100 focus:border-blue-500 focus:outline-none"
					bind:value={selectedRoot}
				>
					{#each roots as root}
						<option value={root}>
							{root.label ?? root.name} - {root.path}
						</option>
					{/each}
				</select>
				{#if selectedRoot?.description}
					<p class="text-xs text-zinc-500">{selectedRoot.description}</p>
				{/if}
			</div>

			<!-- Sessions list -->
			<div class="space-y-2">
				<h2 class="text-sm font-medium text-zinc-300">Existing Sessions</h2>
				<SessionList {sessions} loading={loadingSessions} onResume={handleResumeSession} />
			</div>

			<!-- New session form -->
			<div class="space-y-2">
				<h2 class="text-sm font-medium text-zinc-300">New Session</h2>
				<NewSessionForm {rigs} onLaunch={handleLaunchSession} />
			</div>
		{/if}
	</div>
</div>
