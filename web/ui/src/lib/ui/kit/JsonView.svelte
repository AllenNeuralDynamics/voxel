<script lang="ts">
	import JsonView from './JsonView.svelte';

	interface Props {
		data: unknown;
		expandDepth?: number;
		/** @internal current recursion depth */
		depth?: number;
	}

	let { data, expandDepth = 1, depth = 0 }: Props = $props();

	type Entry = { key: string; value: unknown };

	let entries: Entry[] = $derived.by(() => {
		if (data == null || typeof data !== 'object') return [];
		if (Array.isArray(data)) return data.map((v, i) => ({ key: String(i), value: v }));
		return Object.entries(data as Record<string, unknown>).map(([k, v]) => ({ key: k, value: v }));
	});

	function isContainer(value: unknown): value is Record<string, unknown> | unknown[] {
		return value != null && typeof value === 'object';
	}

	function summary(value: unknown): string {
		if (Array.isArray(value)) return `[${value.length}]`;
		if (typeof value === 'object' && value !== null) return `{${Object.keys(value).length}}`;
		return '';
	}

	function formatPrimitive(value: unknown): string {
		if (value === null || value === undefined) return 'null';
		if (typeof value === 'boolean') return value ? 'true' : 'false';
		if (typeof value === 'number') {
			if (Number.isInteger(value)) return String(value);
			return value.toPrecision(6).replace(/\.?0+$/, '');
		}
		return String(value);
	}
</script>

{#if entries.length > 0}
	<div class="space-y-px text-xs">
		{#each entries as { key, value } (key)}
			{#if isContainer(value)}
				<details open={depth < expandDepth}>
					<summary
						class="flex cursor-pointer list-none items-center gap-1.5 px-1 py-0.5 select-none [&::-webkit-details-marker]:hidden"
					>
						<svg
							class="h-3 w-3 shrink-0 text-muted-foreground/60 transition-transform [[open]>&]:rotate-90"
							viewBox="0 0 16 16"
							fill="currentColor"
						>
							<path d="M6 4l4 4-4 4z" />
						</svg>
						<span class="text-foreground">{key}</span>
						<span class="text-muted-foreground/60">{summary(value)}</span>
					</summary>
					<div class="ml-2 border-l border-border/50 pl-2">
						<JsonView data={value} depth={depth + 1} {expandDepth} />
					</div>
				</details>
			{:else}
				<div class="flex items-baseline gap-2 px-1 py-0.5">
					<span class="shrink-0 text-muted-foreground">{key}</span>
					<span class="font-mono text-foreground">{formatPrimitive(value)}</span>
				</div>
			{/if}
		{/each}
	</div>
{:else if data != null && typeof data !== 'object'}
	<span class="font-mono text-xs text-foreground">{formatPrimitive(data)}</span>
{/if}
