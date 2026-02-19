<script lang="ts">
	import type { Session } from '$lib/main';
	import ProfileSelector from '$lib/ui/ProfileSelector.svelte';
	import DeviceFilterToggle, { type DeviceFilter } from '$lib/ui/DeviceFilterToggle.svelte';
	import ChannelSection from '$lib/ui/ChannelSection.svelte';
	import ClientStatus from '$lib/ui/ClientStatus.svelte';
	import Icon from '@iconify/svelte';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	let deviceFilter = $state<DeviceFilter>('all');
	let showHistograms = $state(true);
</script>

<aside class="flex h-full w-lg min-w-96 flex-col border-r border-border bg-card">
	<div class="space-y-3 border-b border-border p-4">
		<ProfileSelector {session} />
		<div class="flex items-center">
			<div class="flex-1">
				<DeviceFilterToggle bind:value={deviceFilter} onValueChange={(v) => (deviceFilter = v)} />
			</div>
			<div class="mx-2 h-4 w-px bg-border"></div>
			<button
				onclick={() => (showHistograms = !showHistograms)}
				class="flex cursor-pointer items-center justify-center rounded-full p-1 transition-all hover:bg-accent {showHistograms
					? ' text-success '
					: ' text-danger'}"
				aria-label={showHistograms ? 'Hide histograms' : 'Show histograms'}
				title={showHistograms ? 'Hide histograms' : 'Show histograms'}
			>
				<Icon icon="et:bargraph" width="18" height="18" />
			</button>
		</div>
	</div>

	{#if session.previewState.channels.length === 0}
		<div class="flex flex-1 items-center justify-center p-4">
			<p class="text-sm text-muted-foreground">No channels available</p>
		</div>
	{:else}
		<div class="flex flex-1 flex-col overflow-y-auto">
			{#each session.previewState.channels as channel (channel.idx)}
				{#if channel.name}
					<div>
						<ChannelSection
							{channel}
							previewer={session.previewState}
							devices={session.devices}
							{deviceFilter}
							{showHistograms}
							catalog={session.previewState.catalog}
						/>
					</div>
					<div class="border-t border-border"></div>
				{/if}
			{/each}
		</div>
	{/if}

	<footer class="mt-auto flex p-4">
		<ClientStatus client={session.client} />
	</footer>
</aside>
