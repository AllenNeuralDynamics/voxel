<script lang="ts">
	import type { LogMessage } from '$lib/main';
	import {
		BugOutline,
		InformationOutline,
		AlertOutline,
		AlertCircleOutline,
		CircleSmall,
		DeleteOutline
	} from '$lib/icons';
	import type { Component } from 'svelte';

	const { logs, onClear }: { logs: LogMessage[]; onClear?: () => void } = $props();

	let container: HTMLDivElement;

	// Auto-scroll to bottom when new logs arrive
	$effect(() => {
		if (container && logs.length > 0) {
			container.scrollTop = container.scrollHeight;
		}
	});

	function getLevelColor(level: LogMessage['level']): string {
		switch (level) {
			case 'debug':
				return 'text-fg-muted';
			case 'info':
				return 'text-info';
			case 'warning':
				return 'text-warning';
			case 'error':
				return 'text-danger';
			default:
				return 'text-fg-muted';
		}
	}

	const levelIcons: Record<string, Component> = {
		debug: BugOutline,
		info: InformationOutline,
		warning: AlertOutline,
		error: AlertCircleOutline
	};

	function formatTime(timestamp: string): string {
		const date = new Date(timestamp);
		return date.toLocaleTimeString(undefined, {
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit',
			hour12: false
		});
	}

	function truncateMiddle(str: string, maxLen: number): string {
		if (str.length <= maxLen) return str;
		const half = Math.floor((maxLen - 1) / 2);
		return str.slice(0, half) + '…' + str.slice(-(maxLen - half - 1));
	}
</script>

<div class="flex h-full flex-col overflow-hidden">
	<div class="mb-2 flex shrink-0 items-center justify-between">
		<h2 class="text-fg text-base font-medium">Log</h2>
		{#if onClear}
			<button
				onclick={onClear}
				class="text-fg-muted hover:bg-element-hover hover:text-fg flex items-center gap-1 rounded px-2 py-1 text-sm transition-colors"
				title="Clear logs"
			>
				<DeleteOutline width="14" height="14" />
				Clear
			</button>
		{/if}
	</div>
	<div
		bind:this={container}
		class="log-container bg-canvas min-h-0 flex-1 overflow-y-auto rounded border border-border font-mono text-sm"
	>
		{#if logs.length === 0}
			<div class="text-fg-muted flex h-full items-center justify-center">Waiting for logs...</div>
		{:else}
			<div class="space-y-0.5 p-2">
				{#each logs as log, i (i)}
					{@const LevelIcon = levelIcons[log.level] ?? CircleSmall}
					<div class="flex items-center gap-2">
						<span class="text-fg-muted/50 w-[8ch] shrink-0">{formatTime(log.timestamp)}</span>
						<span class="text-fg-muted w-[42ch] shrink-0" title={log.logger}>{truncateMiddle(log.logger, 42)}</span>
						<span class="text-fg min-w-0 flex-1">{log.message}</span>
						<span class="shrink-0 {getLevelColor(log.level)}" title={log.level}>
							<LevelIcon width="14" height="14" />
						</span>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>

<style>
	.log-container {
		scrollbar-width: thin;
		scrollbar-color: var(--border) transparent;
	}

	.log-container::-webkit-scrollbar {
		width: 6px;
	}

	.log-container::-webkit-scrollbar-track {
		background: transparent;
	}

	.log-container::-webkit-scrollbar-thumb {
		background-color: var(--border);
		border-radius: 3px;
	}

	.log-container::-webkit-scrollbar-thumb:hover {
		background-color: var(--fg-muted);
	}
</style>
