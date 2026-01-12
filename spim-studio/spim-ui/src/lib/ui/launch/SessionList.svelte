<script lang="ts">
	import type { SessionDirectory } from '$lib/core';

	const {
		sessions,
		loading,
		onResume
	}: {
		sessions: SessionDirectory[];
		loading: boolean;
		onResume: (session: SessionDirectory) => void;
	} = $props();

	function formatDate(isoString: string): string {
		const date = new Date(isoString);
		return date.toLocaleDateString(undefined, {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}
</script>

<div class="rounded border border-zinc-700 bg-zinc-900">
	{#if loading}
		<div class="flex items-center justify-center py-8">
			<div class="h-5 w-5 animate-spin rounded-full border-2 border-zinc-500 border-t-zinc-300"></div>
			<span class="ml-2 text-sm text-zinc-400">Loading sessions...</span>
		</div>
	{:else if sessions.length === 0}
		<div class="py-8 text-center text-sm text-zinc-500">No sessions found in this root</div>
	{:else}
		<ul class="divide-y divide-zinc-700">
			{#each sessions as session}
				<li class="group">
					<button
						class="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-zinc-800"
						onclick={() => onResume(session)}
					>
						<div class="min-w-0 flex-1">
							<div class="truncate font-medium text-zinc-100">{session.name}</div>
							<div class="mt-0.5 text-xs text-zinc-500">
								<span class="rounded bg-zinc-800 px-1.5 py-0.5">{session.rig_name}</span>
								<span class="ml-2">{formatDate(session.modified)}</span>
							</div>
						</div>
						<div
							class="ml-4 text-xs text-zinc-500 opacity-0 transition-opacity group-hover:opacity-100"
						>
							Resume
						</div>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>
