<script lang="ts">
	import { DropdownMenu, Popover } from 'bits-ui';
	import Icon from '@iconify/svelte';
	import { isValidHex } from '$lib/utils';
	import type { ColormapCatalog } from '$lib/main';
	import { SvelteSet } from 'svelte/reactivity';

	interface Props {
		label: string;
		colormap: string | null;
		catalog: ColormapCatalog;
		onColormapChange: (colormap: string) => void;
		open?: boolean;
		width?: number;
		triggerClass?: string;
		align?: 'start' | 'center' | 'end';
	}

	let {
		label,
		colormap,
		catalog,
		onColormapChange,
		open = $bindable(false),
		width,
		triggerClass,
		align = 'start'
	}: Props = $props();

	function getTriggerColor(cmap: string | null, cat: ColormapCatalog): string {
		if (!cmap) return '#ffffff';
		for (const group of cat) {
			const stops = group.colormaps[cmap];
			if (stops) return stops[stops.length - 1];
		}
		return cmap.startsWith('#') ? cmap : '#ffffff';
	}

	const triggerColor = $derived(getTriggerColor(colormap, catalog));

	const defaultTriggerClass = 'cursor-pointer text-sm leading-5 font-medium transition-colors hover:brightness-125';

	// ── Grid State ────────────────────────────────────────────────────

	let search = $state('');
	let customHex = $state('');
	let hiddenGroups = $state(new Set<string>());
	const hasFilter = $derived(hiddenGroups.size > 0);

	const searchResults = $derived.by(() => {
		const q = search.trim().toLowerCase();
		if (!q) return null;
		const results: { name: string; stops: string[] }[] = [];
		for (const group of catalog) {
			for (const [name, stops] of Object.entries(group.colormaps)) {
				if (name.toLowerCase().includes(q)) results.push({ name, stops });
			}
		}
		return results;
	});

	function stopsToGradient(stops: string[]): string {
		return `linear-gradient(to right, ${stops.join(', ')})`;
	}

	function pick(name: string) {
		onColormapChange(name);
		open = false;
	}

	function submitHex() {
		const hex = customHex.trim();
		if (isValidHex(hex)) {
			onColormapChange(hex);
			customHex = '';
			open = false;
		}
	}
</script>

<Popover.Root bind:open>
	<Popover.Trigger
		class={triggerClass ?? defaultTriggerClass}
		style="color: {triggerColor};"
		aria-label="Pick colormap for {label}"
	>
		{label}
	</Popover.Trigger>

	<Popover.Portal>
		<Popover.Content
			class="z-50 flex flex-col-reverse rounded-t border border-zinc-700 bg-zinc-900 shadow-xl outline-none {width
				? ''
				: 'w-72'}"
			style={width ? `width: ${width}px;` : undefined}
			side="top"
			sideOffset={0}
			{align}
		>
			<div class="flex items-center gap-1.5 px-2 py-2">
				<input
					type="text"
					bind:value={search}
					placeholder="Search colormaps..."
					class="h-6 min-w-0 flex-1 rounded border border-zinc-600 bg-zinc-800 px-1.5 text-[0.65rem] text-zinc-200 placeholder-zinc-500 focus:border-ring focus:outline-none"
				/>
				<DropdownMenu.Root>
					<DropdownMenu.Trigger
						class="flex h-6 w-6 shrink-0 items-center justify-center rounded border border-zinc-600 bg-zinc-800 transition-colors hover:bg-zinc-700 {hasFilter
							? 'text-zinc-200'
							: 'text-zinc-400'}"
						aria-label="Filter groups"
					>
						<Icon icon="mdi:filter-variant" width="14" height="14" />
					</DropdownMenu.Trigger>
					<DropdownMenu.Portal>
						<DropdownMenu.Content
							class="z-60 min-w-32 rounded border border-zinc-700 bg-zinc-900 p-1 shadow-xl outline-none"
							side="top"
							sideOffset={4}
							align="end"
						>
							{#each catalog as group (group.uid)}
								<DropdownMenu.CheckboxItem
									closeOnSelect={false}
									checked={!hiddenGroups.has(group.uid)}
									onCheckedChange={(checked) => {
										const next = new SvelteSet(hiddenGroups);
										if (checked) next.delete(group.uid);
										else next.add(group.uid);
										hiddenGroups = next;
									}}
									class="flex cursor-default items-center gap-1.5 rounded-sm px-1.5 py-1 text-[0.6rem] text-muted-foreground outline-none select-none data-highlighted:bg-accent data-highlighted:text-foreground"
								>
									{#snippet children({ checked })}
										<span class="inline-flex h-3 w-3 shrink-0 items-center justify-center">
											{#if checked}
												<Icon icon="mdi:check" class="h-3 w-3 text-foreground" />
											{/if}
										</span>
										<span>{group.label}</span>
									{/snippet}
								</DropdownMenu.CheckboxItem>
							{/each}
						</DropdownMenu.Content>
					</DropdownMenu.Portal>
				</DropdownMenu.Root>
			</div>

			<div class="max-h-80 overflow-y-auto border-y border-zinc-700 px-2">
				{#if searchResults}
					{#if searchResults.length > 0}
						<div class="swatch-grid pb-2">
							{#each searchResults as { name, stops } (name)}
								<button
									type="button"
									onclick={() => pick(name)}
									class="swatch-row {colormap === name ? 'selected' : ''}"
									aria-label="Select colormap {name}"
								>
									<span class="swatch-gradient" style="background: {stopsToGradient(stops)}"></span>
									<span class="truncate text-[0.6rem] text-muted-foreground">{name}</span>
								</button>
							{/each}
						</div>
					{:else}
						<div class="pb-2 text-[0.65rem] text-muted-foreground">No matches</div>
					{/if}
				{:else}
					{#each catalog as group (group.uid)}
						{#if !hiddenGroups.has(group.uid)}
							<div
								class="pt-1 pb-0.5 text-[0.5rem] font-medium tracking-wide text-muted-foreground uppercase opacity-60"
							>
								{group.label}
							</div>
							<div class="swatch-grid pb-2">
								{#each Object.entries(group.colormaps) as [name, stops] (name)}
									<button
										type="button"
										onclick={() => pick(name)}
										class="swatch-row {colormap === name ? 'selected' : ''}"
										aria-label="Select colormap {name}"
									>
										<span class="swatch-gradient" style="background: {stopsToGradient(stops)}"></span>
										<span class="truncate text-[0.6rem] text-muted-foreground">{name}</span>
									</button>
								{/each}
							</div>
						{/if}
					{/each}
				{/if}
			</div>

			<div class="flex items-center gap-1.5 px-2 py-2">
				<input
					type="text"
					bind:value={customHex}
					onkeydown={(e) => {
						if (e.key === 'Enter') submitHex();
					}}
					placeholder={triggerColor}
					size="5"
					class="h-6 min-w-0 flex-1 rounded border border-l-[3px] border-zinc-600 border-l-(--hex-color) bg-zinc-800 px-1.5 font-mono text-[0.65rem] text-zinc-200 placeholder:text-muted-foreground focus:border-ring focus:outline-none"
					style:--hex-color={triggerColor}
				/>
				<button
					type="button"
					onclick={submitHex}
					class="flex h-6 w-6 shrink-0 items-center justify-center rounded border border-zinc-600 bg-zinc-800 text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-zinc-200"
					aria-label="Apply custom hex color"
				>
					<Icon icon="mdi:check" width="14" height="14" />
				</button>
			</div>
		</Popover.Content>
	</Popover.Portal>
</Popover.Root>

<style>
	.swatch-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(5.5rem, 1fr));
		gap: 0.375rem 0.125rem;
	}

	.swatch-row {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.125rem 0.25rem;
		border-radius: 2px;
		cursor: pointer;
		transition: background 0.15s;
		min-width: 0;
	}

	.swatch-row:hover {
		background: var(--color-accent);
	}

	.swatch-row.selected {
		background: var(--color-accent);
		outline: 1px solid var(--color-border);
	}

	.swatch-gradient {
		flex-shrink: 0;
		width: 2.5rem;
		height: 0.625rem;
		border-radius: 1px;
		border: 1px solid oklch(1 0 0 / 0.1);
	}

	.swatch-row:hover span,
	.swatch-row.selected span {
		color: var(--color-foreground);
	}
</style>
