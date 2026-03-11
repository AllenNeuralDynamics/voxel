<script lang="ts">
	import { getAppContext } from '$lib/context';
	import { page } from '$app/state';
	import { cn, sanitizeString } from '$lib/utils';
	import DeviceBrowser from '$lib/ui/device/DeviceBrowser.svelte';
	import CameraConfig from './CameraConfig.svelte';
	import LaserConfig from './LaserConfig.svelte';
	import DaqConfig from './DaqConfig.svelte';

	const app = getAppContext();
	const session = $derived(app.session!);
	const deviceId = $derived(page.params.id!);
	const daqDeviceId = $derived(session.config.daq.device);
	const devicesManager = $derived(session.devices);
	const device = $derived(devicesManager.getDevice(deviceId));
</script>

{#if session.devices.devices.has(deviceId)}
	{#if deviceId in session.cameras}
		<CameraConfig {session} {deviceId} />
	{:else if deviceId in session.lasers}
		<LaserConfig {session} {deviceId} />
	{:else if deviceId === daqDeviceId}
		<DaqConfig {session} {deviceId} />
	{:else}
		<!-- Generic device config -->
		<section class="flex h-full flex-col gap-6">
			<div class="flex items-center justify-between">
				<h2 class="text-sm font-medium text-foreground">{sanitizeString(deviceId)}</h2>
				<span
					class={cn('h-2 w-2 rounded-full', device?.connected ? 'bg-success' : 'bg-muted-foreground/30')}
					title={device?.connected ? 'Connected' : 'Disconnected'}
				></span>
			</div>

			{#if device?.connected}
				<div class="min-h-0 flex-1 space-y-6">
					<DeviceBrowser {deviceId} {devicesManager} />
				</div>
			{:else}
				<div class="flex items-center justify-center py-12">
					<p class="text-sm text-muted-foreground">Device not available</p>
				</div>
			{/if}
		</section>
	{/if}
{/if}
