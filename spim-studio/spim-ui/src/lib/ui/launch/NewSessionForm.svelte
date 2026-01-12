<script lang="ts">
	import type { SessionRoot } from '$lib/core';

	const {
		roots,
		rigs,
		onLaunch
	}: {
		roots: SessionRoot[];
		rigs: string[];
		onLaunch: (rootName: string, sessionName: string, rigConfig?: string) => void;
	} = $props();

	let sessionName = $state('');
	let selectedRoot = $state<string | undefined>(undefined);
	let selectedRig = $state<string | undefined>(undefined);
	let launching = $state(false);

	// Auto-select first root when available
	$effect(() => {
		if (!selectedRoot && roots.length > 0) {
			selectedRoot = roots[0].name;
		}
	});

	// Auto-select first rig when available
	$effect(() => {
		if (!selectedRig && rigs.length > 0) {
			selectedRig = rigs[0];
		}
	});

	const isValid = $derived(sessionName.trim().length > 0 && selectedRoot && selectedRig);

	async function handleSubmit(e: Event) {
		e.preventDefault();
		if (!isValid || launching || !selectedRoot) return;

		launching = true;
		try {
			await onLaunch(selectedRoot, sessionName.trim(), selectedRig);
		} finally {
			launching = false;
		}
	}
</script>

<form class="space-y-4 rounded border border-zinc-700 bg-zinc-900 p-4" onsubmit={handleSubmit}>
	<div class="grid grid-cols-3 gap-4">
		<!-- Root selector -->
		<div class="space-y-1">
			<label for="root-select" class="block text-xs text-zinc-400">Session Root</label>
			<select
				id="root-select"
				bind:value={selectedRoot}
				class="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
			>
				{#each roots as root (root.name)}
					<option value={root.name}>{root.label ?? root.name}</option>
				{/each}
			</select>
		</div>

		<!-- Session name -->
		<div class="space-y-1">
			<label for="session-name" class="block text-xs text-zinc-400">Session Name</label>
			<input
				id="session-name"
				type="text"
				bind:value={sessionName}
				placeholder="my-session"
				class="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-blue-500 focus:outline-none"
			/>
		</div>

		<!-- Rig selector -->
		<div class="space-y-1">
			<label for="rig-select" class="block text-xs text-zinc-400">Rig Configuration</label>
			<select
				id="rig-select"
				bind:value={selectedRig}
				class="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
			>
				{#each rigs as rig (rig)}
					<option value={rig}>{rig}</option>
				{/each}
			</select>
		</div>
	</div>

	<button
		type="submit"
		disabled={!isValid || launching}
		class="w-full rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
	>
		{#if launching}
			<span class="inline-flex items-center">
				<span class="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"></span>
				Launching...
			</span>
		{:else}
			Create Session
		{/if}
	</button>
</form>
