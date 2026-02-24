<script lang="ts">
	import LaserControl from '$lib/ui/devices/LaserControl.svelte';
	import CameraControl from '$lib/ui/devices/CameraControl.svelte';
	import type { Session } from '$lib/main';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	const laserIds = $derived([
		...new Set(
			session.previewState.channels
				.filter((ch) => ch.config?.illumination)
				.map((ch) => ch.config!.illumination!)
		)
	]);

	const cameraIds = $derived([
		...new Set(
			session.previewState.channels
				.filter((ch) => ch.config?.detection)
				.map((ch) => ch.config!.detection!)
		)
	]);
</script>

<div class="h-full overflow-auto bg-card p-4">
	{#if laserIds.length === 0 && cameraIds.length === 0}
		<div class="flex h-full items-center justify-center">
			<p class="text-xs text-muted-foreground">No devices in active profile</p>
		</div>
	{:else}
		<div class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3">
			{#each laserIds as deviceId (deviceId)}
				<LaserControl {deviceId} devicesManager={session.devices} />
			{/each}
			{#each cameraIds as deviceId (deviceId)}
				<CameraControl {deviceId} devicesManager={session.devices} />
			{/each}
		</div>
	{/if}
</div>
