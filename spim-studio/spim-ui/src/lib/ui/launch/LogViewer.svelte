<script lang="ts">
	import type { LogMessage } from '$lib/core';

	const { logs }: { logs: LogMessage[] } = $props();

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
				return 'text-zinc-300';
			case 'warning':
				return 'text-amber-400';
			case 'error':
				return 'text-rose-400';
			default:
				return 'text-zinc-400';
		}
	}

	function formatTime(timestamp: string): string {
		const date = new Date(timestamp);
		return date.toLocaleTimeString(undefined, {
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		});
	}
</script>

<div
	bind:this={container}
	class="h-64 overflow-y-auto rounded border border-zinc-700 bg-zinc-900 font-mono text-xs"
>
	{#if logs.length === 0}
		<div class="flex h-full items-center justify-center text-zinc-500">Waiting for logs...</div>
	{:else}
		<div class="p-2 space-y-0.5">
			{#each logs as log}
				<div class="flex gap-2 {getLevelColor(log.level)}">
					<span class="shrink-0 text-zinc-600">{formatTime(log.timestamp)}</span>
					<span class="shrink-0 w-14 text-right text-zinc-500">[{log.logger}]</span>
					<span class="break-all">{log.message}</span>
				</div>
			{/each}
		</div>
	{/if}
</div>
