<script lang="ts">
	import type { Session } from '$lib/main';
	import { cn, sanitizeString } from '$lib/utils';
	import DynamicProperties from './DynamicProperties.svelte';

	interface Props {
		session: Session;
		deviceId: string;
	}

	let { session, deviceId }: Props = $props();

	let devicesManager = $derived(session.devices);
	let device = $derived(devicesManager.getDevice(deviceId));
</script>

<section class="flex h-full flex-col gap-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<h2 class="text-sm font-medium text-foreground">{sanitizeString(deviceId)}</h2>
		<span
			class={cn('h-2 w-2 rounded-full', device?.connected ? 'bg-success' : 'bg-muted-foreground/30')}
			title={device?.connected ? 'Connected' : 'Disconnected'}
		></span>
	</div>

	{#if device?.connected}
		<div class="min-h-0 flex-1 space-y-6">
			<DynamicProperties {deviceId} {devicesManager} />
		</div>
	{:else}
		<div class="flex items-center justify-center py-12">
			<p class="text-sm text-muted-foreground">Device not available</p>
		</div>
	{/if}
</section>
