<script lang="ts">
	import type { Session } from '$lib/main';
	import { cn, sanitizeString } from '$lib/utils';
	import ChannelsConfig from './ChannelsConfig.svelte';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	const config = $derived(session.config);
	const daqDeviceId = $derived(config.daq.device);

	type NavTarget = { type: 'device'; id: string } | { type: 'channels' };
	let activeNav = $state<NavTarget>({ type: 'channels' });

	function isActive(target: NavTarget): boolean {
		if (activeNav.type !== target.type) return false;
		if (target.type === 'device' && activeNav.type === 'device') return activeNav.id === target.id;
		return true;
	}

	function navClass(target: NavTarget): string {
		return cn(
			'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-xs cursor-pointer transition-colors',
			isActive(target)
				? 'bg-accent text-accent-foreground'
				: 'text-muted-foreground hover:bg-muted hover:text-foreground'
		);
	}
</script>

<div class="flex h-full">
	<!-- Sidebar Navigation -->
	<aside class="flex w-52 shrink-0 flex-col overflow-auto border-r border-border bg-card p-3">
		<!-- Channels -->
		<nav class="space-y-0.5">
			<button onclick={() => (activeNav = { type: 'channels' })} class={navClass({ type: 'channels' })}>
				Channels
			</button>
		</nav>

		<div class="my-3 border-t border-border"></div>

		<!-- Devices -->
		<div>
			<h3 class="mb-1 px-2 text-[0.65rem] font-medium uppercase tracking-wide text-muted-foreground">
				Devices
			</h3>
			<nav class="space-y-0.5">
				{#each [...session.devices.devices] as [id, device] (id)}
					<button onclick={() => (activeNav = { type: 'device', id })} class={navClass({ type: 'device', id })}>
						<span class="truncate">{sanitizeString(id)}</span>
						<span
							class={cn(
								'h-1.5 w-1.5 shrink-0 rounded-full',
								device.connected ? 'bg-success' : 'bg-muted-foreground/30'
							)}
							title={device.connected ? 'Connected' : 'Disconnected'}
						></span>
					</button>
				{/each}
			</nav>
		</div>
	</aside>

	<!-- Main Content -->
	<div class="flex-1 overflow-auto p-6">
		{#if activeNav.type === 'channels'}
			<ChannelsConfig {session} />
		{:else if activeNav.type === 'device'}
			<!-- Device Detail -->
			{#if activeNav.id === daqDeviceId}
				<!-- DAQ device page — show acquisition ports -->
				<section>
					<h3 class="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
						Acquisition Ports
					</h3>
					<div class="space-y-1">
						{#each Object.entries(config.daq.acq_ports) as [deviceId, port] (deviceId)}
							<div class="flex items-center justify-between rounded px-2 py-1.5 text-xs">
								<span class="text-foreground">{deviceId}</span>
								<span class="font-mono text-muted-foreground">{port}</span>
							</div>
						{/each}
					</div>
				</section>
			{:else}
				<div class="flex items-center justify-center py-12">
					<p class="text-sm text-muted-foreground">
						{sanitizeString(activeNav.id)} — device details coming soon
					</p>
				</div>
			{/if}
		{/if}
	</div>
</div>
