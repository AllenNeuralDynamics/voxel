<script lang="ts">
	import { Tooltip } from 'bits-ui';
	import Icon from '@iconify/svelte';
	import type { ChannelConfig } from '$lib/client';

	interface Props {
		name: string;
		label?: string | null;
		config?: ChannelConfig;
	}

	let { name, label, config }: Props = $props();

	const filterEntries = $derived<[string, string][]>(config?.filters ? Object.entries(config.filters) : []);
</script>

<Tooltip.Provider>
	<Tooltip.Root delayDuration={150}>
		<Tooltip.Trigger
			class="flex items-center rounded p-1 text-zinc-300 transition-colors hover:bg-zinc-800"
			aria-label="Channel info"
		>
			<Icon icon="mdi:information-outline" width="14" height="14" />
		</Tooltip.Trigger>
		<Tooltip.Content
			class="z-50 w-64 rounded-md border border-zinc-700 bg-zinc-900 p-3 text-left text-xs text-zinc-200 shadow-xl outline-none"
			sideOffset={4}
			align="end"
		>
			<div class="space-y-2">
				<div>
					<p class="text-sm font-semibold text-zinc-100">
						{label ?? name}
					</p>
					<p class="mt-1 text-xs text-zinc-300">
						{config?.desc ?? 'No description available.'}
					</p>
				</div>
				{#if config?.illumination || filterEntries.length || config?.detection}
					<div class="space-y-1 border-t border-zinc-800 pt-2 text-[0.7rem] text-zinc-300">
						{#if config?.illumination}
							<div class="flex justify-between gap-2">
								<span class="text-zinc-400">Illumination</span>
								<span class="text-right text-zinc-200">{config.illumination}</span>
							</div>
						{/if}
						{#if config?.detection}
							<div class="flex justify-between gap-2">
								<span class="text-zinc-400">Detection</span>
								<span class="text-right text-zinc-200">{config.detection}</span>
							</div>
						{/if}
						{#if filterEntries.length}
							<div class="space-y-1">
								<div class="mb-1 border-b border-zinc-800 pt-1 text-zinc-500/90">Filters</div>
								<div class="space-y-1">
									{#each filterEntries as [filterName, filterValue] (filterName)}
										<div class="flex justify-between gap-2">
											<span class="text-zinc-400">{filterName}:</span>
											<span class="text-right text-zinc-200">{filterValue}</span>
										</div>
									{/each}
								</div>
							</div>
						{/if}
					</div>
				{/if}
			</div>
		</Tooltip.Content>
	</Tooltip.Root>
</Tooltip.Provider>
