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
		return name.replace(/[-_]/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
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
				class="group flex w-full items-center gap-4 rounded border border-border bg-card px-4 py-3 text-left transition-colors hover:border-foreground/20 hover:bg-accent"
				onclick={() => onResume(session)}
			>
				<!-- Content -->
				<div class="min-w-0 flex-1 space-y-2">
					<!-- Session name -->
					<div class="flex items-center gap-2">
						<Icon icon="mdi:flask-outline" width="14" height="14" class="shrink-0 text-primary" />
						<span class="truncate text-sm font-medium text-foreground">{formatSessionName(session.name)}</span>
					</div>
					<!-- Meta row -->
					<div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
						<span class="flex items-center gap-1.5 text-foreground">
							<Icon icon="mdi:folder-outline" width="12" height="12" class="text-warning" />
							{session.root_name}
						</span>
						<span class="flex items-center gap-1.5 text-muted-foreground">
							<Icon icon="mdi:cog-outline" width="12" height="12" class="text-muted-foreground" />
							{session.rig_name}
						</span>
						<span class="text-muted-foreground">
							{formatRelativeTime(session.modified)}
						</span>
					</div>
				</div>

				<!-- Resume indicator -->
				<div
					class="flex shrink-0 items-center gap-1.5 rounded bg-secondary px-2.5 py-1 text-xs text-secondary-foreground transition-colors group-hover:bg-success group-hover:text-success-fg"
				>
					<span>Resume</span>
					<Icon icon="mdi:arrow-right" width="14" height="14" />
				</div>
			</button>
		{/each}
	</div>
{/if}
