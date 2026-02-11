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
</script>

{#if loading}
	<div class="flex items-center justify-center rounded border border-border bg-card py-12">
		<div class="h-5 w-5 animate-spin rounded-full border-2 border-border border-t-muted-foreground"></div>
		<span class="ml-3 text-sm text-muted-foreground">Loading sessions...</span>
	</div>
{:else if sessions.length === 0}
	<div class="flex flex-col items-center justify-center rounded border border-dashed border-border bg-card py-10">
		<Icon icon="mdi:folder-open-outline" width="32" height="32" class="text-muted-foreground/50" />
		<p class="mt-2 text-sm text-muted-foreground">No recent sessions</p>
		<p class="text-xs text-muted-foreground/60">Create a new session to get started</p>
	</div>
{:else}
	<div class="space-y-2">
		{#each sessions as session (session.path)}
			<button
				class="group flex w-full items-center gap-3 rounded border border-border bg-card px-3 py-2.5 text-left transition-colors hover:border-foreground/20 hover:bg-accent"
				onclick={() => onResume(session)}
			>
				<span class="min-w-0 flex-1 truncate text-xs text-foreground">
					<span class="text-muted-foreground">{session.root_name} /</span>
					{session.name}
				</span>
				<span class="shrink-0 text-[0.65rem] text-muted-foreground/60">{formatRelativeTime(session.modified)}</span>
				<Icon
					icon="mdi:arrow-right"
					width="14"
					height="14"
					class="shrink-0 text-muted-foreground/30 transition-colors group-hover:text-foreground"
				/>
			</button>
		{/each}
	</div>
{/if}
