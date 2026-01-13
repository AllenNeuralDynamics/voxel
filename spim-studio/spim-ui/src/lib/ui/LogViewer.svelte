<script lang="ts">
	import type { LogMessage } from '$lib/core';
	import Icon from '@iconify/svelte';

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
				return 'text-zinc-500';
			case 'info':
				return 'text-blue-400';
			case 'warning':
				return 'text-amber-400';
			case 'error':
				return 'text-rose-400';
			default:
				return 'text-zinc-400';
		}
	}

	function getLevelIcon(level: LogMessage['level']): string {
		switch (level) {
			case 'debug':
				return 'mdi:bug-outline';
			case 'info':
				return 'mdi:information-outline';
			case 'warning':
				return 'mdi:alert-outline';
			case 'error':
				return 'mdi:alert-circle-outline';
			default:
				return 'mdi:circle-small';
		}
	}

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
		<h2 class="text-sm font-medium text-zinc-300">Log</h2>
		{#if onClear}
			<button
				onclick={onClear}
				class="flex items-center gap-1 rounded px-2 py-1 text-xs text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-300"
				title="Clear logs"
			>
				<Icon icon="mdi:delete-outline" width="14" height="14" />
				Clear
			</button>
		{/if}
	</div>
	<div
		bind:this={container}
		class="log-container min-h-0 flex-1 overflow-y-auto rounded border border-zinc-700 bg-zinc-800 font-mono text-xs"
	>
		{#if logs.length === 0}
			<div class="flex h-full items-center justify-center text-zinc-500">Waiting for logs...</div>
		{:else}
			<div class="space-y-0.5 p-2">
				{#each logs as log, i (i)}
					<div class="flex items-center gap-2">
						<!-- Time: fixed 8 chars "HH:MM:SS" -->
						<span class="w-[8ch] shrink-0 text-zinc-600">{formatTime(log.timestamp)}</span>
						<!-- Logger: fixed width, middle-truncated -->
						<span class="w-[36ch] shrink-0 text-zinc-500" title={log.logger}
							>{truncateMiddle(log.logger, 36)}</span
						>
						<!-- Message: fills remaining space -->
						<span class="min-w-0 flex-1 text-zinc-300">{log.message}</span>
						<!-- Level: icon at end -->
						<span class="shrink-0 {getLevelColor(log.level)}" title={log.level}>
							<Icon icon={getLevelIcon(log.level)} width="14" height="14" />
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
		scrollbar-color: #3f3f46 transparent;
	}

	.log-container::-webkit-scrollbar {
		width: 6px;
	}

	.log-container::-webkit-scrollbar-track {
		background: transparent;
	}

	.log-container::-webkit-scrollbar-thumb {
		background-color: #3f3f46;
		border-radius: 3px;
	}

	.log-container::-webkit-scrollbar-thumb:hover {
		background-color: #52525b;
	}
</style>
