<script lang="ts">
	import type { Session } from '$lib/main';
	import { cn, sanitizeString } from '$lib/utils';
	import DeviceBrowser from '$lib/ui/device/DeviceBrowser.svelte';

	interface Props {
		session: Session;
		deviceId: string;
	}

	let { session, deviceId }: Props = $props();

	let devicesManager = $derived(session.devices);
	let device = $derived(devicesManager.getDevice(deviceId));
	const acqPorts = $derived(Object.entries(session.config.daq.acq_ports));
</script>

<section class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<h2 class="text-fg text-sm font-medium">{sanitizeString(deviceId)}</h2>
		<span
			class={cn('h-2 w-2 rounded-full', device?.connected ? 'bg-success' : 'bg-fg-muted/30')}
			title={device?.connected ? 'Connected' : 'Disconnected'}
		></span>
	</div>

	<div class="max-w-xl space-y-6">
		<!-- Acquisition Ports -->
		{#if acqPorts.length > 0}
			<div class="rounded border border-border bg-card p-3">
				<h4 class="text-fg-muted mb-2 text-[0.65rem] font-medium tracking-wide uppercase">Acquisition Ports</h4>
				<div class="grid gap-1.5 text-xs">
					{#each acqPorts as [portDevice, port] (portDevice)}
						<div class="flex items-center justify-between">
							<span class="text-fg">{portDevice}</span>
							<span class="text-fg-muted font-mono">{port}</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		{#if device?.connected}
			<DeviceBrowser {deviceId} {devicesManager} />
		{:else}
			<div class="flex items-center justify-center py-12">
				<p class="text-fg-muted text-sm">DAQ device not available</p>
			</div>
		{/if}
	</div>
</section>
