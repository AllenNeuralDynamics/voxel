<script lang="ts">
	import { Popover } from 'bits-ui';
	import type { Previewer } from '$lib/preview';
	import type { ProfilesManager } from '$lib/control';

	const { previewer, manager } = $props<{ previewer: Previewer; manager: ProfilesManager }>();

	const connectionEntries = $derived(() => [
		{
			id: 'preview',
			label: 'Preview stream',
			connected: previewer.connectionState,
			description: previewer.statusMessage || (previewer.connectionState ? 'Streaming' : 'Offline')
		},
		{
			id: 'control',
			label: 'Control sync',
			connected: manager.controlConnected,
			description: manager.controlConnected ? 'Realtime updates active' : 'Reconnecting...'
		}
	]);
</script>

<Popover.Root>
	<Popover.Trigger
		class="group flex items-center gap-1 rounded-md border border-transparent  px-1 text-xs text-zinc-300 transition hover:border-zinc-700 hover:bg-zinc-900"
	>
		{#each connectionEntries() as entry (entry.id)}
			<span
				class="inline-flex h-4 w-2 items-center justify-center rounded-full border-0 text-[0.55rem] font-semibold {entry.connected
					? 'border-emerald-500/40 text-emerald-400'
					: 'border-rose-500/40 text-rose-400'}"
				aria-label="{entry.label} status"
			>
				{entry.connected ? '✓' : '×'}
			</span>
		{/each}
	</Popover.Trigger>

	<Popover.Content
		class="z-50 w-44 rounded-lg border border-zinc-800 bg-zinc-900/95 p-1 shadow-xl ring-1 ring-black/20 backdrop-blur"
		sideOffset={6}
		align="start"
	>
		<div class="space-y-1.5">
			{#each connectionEntries() as entry (entry.id)}
				<div class="flex items-start gap-1.5 rounded-md border border-zinc-800/60 bg-zinc-900/70 px-2 py-1">
					<span class="mt-1 inline-flex h-2 w-2 rounded-full {entry.connected ? 'bg-emerald-500' : 'bg-rose-500'}"
					></span>
					<div class="flex flex-col">
						<p class="text-[0.8rem] font-medium text-zinc-100">{entry.label}</p>
						<p class="text-[0.65rem] text-zinc-500">{entry.description}</p>
					</div>
				</div>
			{/each}
		</div>
	</Popover.Content>
</Popover.Root>
