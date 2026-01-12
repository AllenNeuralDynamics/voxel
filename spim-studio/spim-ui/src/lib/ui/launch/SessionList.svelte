<script lang="ts">
	import type { SessionDirectory } from '$lib/core';
	import Icon from '@iconify/svelte';

	const {
		sessions,
		loading,
		onResume
	}: {
		sessions: SessionDirectory[];
		loading: boolean;
		onResume: (session: SessionDirectory) => void;
	} = $props();

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

		return date.toLocaleDateString(undefined, {
			month: 'short',
			day: 'numeric'
		});
	}

	function formatSessionName(name: string): string {
		return name
			.replace(/[-_]/g, ' ')
			.replace(/\b\w/g, (char) => char.toUpperCase());
	}
</script>

{#if loading}
	<div class="flex items-center justify-center rounded border border-zinc-700 bg-zinc-900 py-12">
		<div class="h-5 w-5 animate-spin rounded-full border-2 border-zinc-600 border-t-zinc-300"></div>
		<span class="ml-3 text-sm text-zinc-400">Loading sessions...</span>
	</div>
{:else if sessions.length === 0}
	<div class="flex flex-col items-center justify-center rounded border border-dashed border-zinc-700 bg-zinc-900 py-10">
		<Icon icon="mdi:folder-open-outline" width="32" height="32" class="text-zinc-600" />
		<p class="mt-2 text-sm text-zinc-500">No recent sessions</p>
		<p class="text-xs text-zinc-600">Create a new session to get started</p>
	</div>
{:else}
	<div class="space-y-2">
		{#each sessions as session (session.path)}
			<button
				class="group flex w-full items-center gap-4 rounded border border-zinc-700 bg-zinc-900 px-4 py-3 text-left transition-colors hover:border-zinc-600 hover:bg-zinc-800"
				onclick={() => onResume(session)}
			>
				<!-- Content -->
				<div class="min-w-0 flex-1 space-y-2">
					<!-- Session name -->
					<div class="flex items-center gap-2">
						<Icon icon="mdi:flask-outline" width="14" height="14" class="shrink-0 text-blue-400" />
						<span class="truncate text-sm font-medium text-zinc-100">{formatSessionName(session.name)}</span>
					</div>
					<!-- Meta row -->
					<div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
						<span class="flex items-center gap-1.5 text-zinc-200">
							<Icon icon="mdi:folder-outline" width="12" height="12" class="text-amber-400" />
							{session.root_name}
						</span>
						<span class="flex items-center gap-1.5 text-zinc-300">
							<Icon icon="mdi:cog-outline" width="12" height="12" class="text-zinc-400" />
							{session.rig_name}
						</span>
						<span class="text-zinc-400">
							{formatRelativeTime(session.modified)}
						</span>
					</div>
				</div>

				<!-- Resume indicator -->
				<div class="flex shrink-0 items-center gap-1.5 rounded bg-zinc-800 px-2.5 py-1 text-xs text-zinc-300 transition-colors group-hover:bg-emerald-600 group-hover:text-white">
					<span>Resume</span>
					<Icon icon="mdi:arrow-right" width="14" height="14" />
				</div>
			</button>
		{/each}
	</div>
{/if}
