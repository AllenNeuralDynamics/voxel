<script lang="ts">
	import { getAppContext } from '$lib/context';
	import { page } from '$app/state';
	import { CameraConfig, LaserConfig, DaqConfig, DeviceConfig } from '$lib/ui/configure';

	const app = getAppContext();
	const session = $derived(app.session!);
	const deviceId = $derived(page.params.id!);
	const daqDeviceId = $derived(session.config.daq.device);
</script>

{#if session.devices.devices.has(deviceId)}
	{#if deviceId in session.cameras}
		<CameraConfig {session} {deviceId} />
	{:else if deviceId in session.lasers}
		<LaserConfig {session} {deviceId} />
	{:else if deviceId === daqDeviceId}
		<DaqConfig {session} {deviceId} />
	{:else}
		<DeviceConfig {session} {deviceId} />
	{/if}
{/if}
