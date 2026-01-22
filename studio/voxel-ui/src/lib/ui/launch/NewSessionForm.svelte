<script lang="ts">
	import type { SessionRoot } from '$lib/core';
	import Icon from '@iconify/svelte';

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

	function sanitizeSessionName(name: string): string {
		return name.trim().toLowerCase().replace(/\s+/g, '-');
	}

	async function handleSubmit(e: Event) {
		e.preventDefault();
		if (!isValid || launching || !selectedRoot) return;

		launching = true;
		try {
			await onLaunch(selectedRoot, sanitizeSessionName(sessionName), selectedRig);
		} finally {
			launching = false;
		}
	}
</script>

<form class="space-y-3 rounded border border-zinc-700 bg-zinc-900 p-4" onsubmit={handleSubmit}>
	<!-- Row 1: Root and Rig selectors -->
	<div class="flex gap-4">
		<div class="flex-1 space-y-1.5">
			<label for="root-select" class="flex items-center gap-1.5 text-xs font-medium text-zinc-400">
				<Icon icon="mdi:folder-outline" width="14" height="14" />
				Session Root
			</label>
			<div class="relative">
				<select
					id="root-select"
					bind:value={selectedRoot}
					class="w-full appearance-none rounded border border-zinc-700 bg-zinc-800 py-2 pr-8 pl-3 text-sm text-zinc-100 transition-colors focus:border-blue-500 focus:outline-none"
				>
					{#each roots as root (root.name)}
						<option value={root.name}>{root.label ?? root.name}</option>
					{/each}
				</select>
				<Icon
					icon="mdi:chevron-down"
					width="16"
					height="16"
					class="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 text-zinc-500"
				/>
			</div>
		</div>

		<div class="flex-1 space-y-1.5">
			<label for="rig-select" class="flex items-center gap-1.5 text-xs font-medium text-zinc-400">
				<Icon icon="mdi:cog-outline" width="14" height="14" />
				Rig Configuration
			</label>
			<div class="relative">
				<select
					id="rig-select"
					bind:value={selectedRig}
					class="w-full appearance-none rounded border border-zinc-700 bg-zinc-800 py-2 pr-8 pl-3 text-sm text-zinc-100 transition-colors focus:border-blue-500 focus:outline-none"
				>
					{#each rigs as rig (rig)}
						<option value={rig}>{rig}</option>
					{/each}
				</select>
				<Icon
					icon="mdi:chevron-down"
					width="16"
					height="16"
					class="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 text-zinc-500"
				/>
			</div>
		</div>
	</div>

	<!-- Row 2: Session name and Create button -->
	<div class="flex items-end gap-4">
		<div class="flex-1 space-y-1.5">
			<label for="session-name" class="flex items-center gap-1.5 text-xs font-medium text-zinc-400">
				<Icon icon="mdi:flask-outline" width="14" height="14" />
				Session Name
			</label>
			<input
				id="session-name"
				type="text"
				bind:value={sessionName}
				placeholder="Enter session name..."
				class="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 transition-colors focus:border-blue-500 focus:outline-none"
			/>
		</div>

		<button
			type="submit"
			disabled={!isValid || launching}
			class="flex shrink-0 items-center gap-2 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-blue-600"
		>
			{#if launching}
				<div class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white"></div>
				<span>Launching...</span>
			{:else}
				<Icon icon="mdi:rocket-launch-outline" width="16" height="16" />
				<span>Create</span>
			{/if}
		</button>
	</div>
</form>
