<script lang="ts">
	import { getAppContext } from '$lib/context';
	import { useSearchParams, createSearchParamsSchema } from 'runed/kit';
	import { sanitizeString, wavelengthToColor } from '$lib/utils';
	import { ProfileConfig } from '$lib/ui/profile';
	import { CameraConfig, LaserConfig, DaqConfig, DeviceConfig } from '$lib/ui/configure';

	type NavTarget = { type: 'device'; id: string } | { type: 'channels' } | { type: 'profile'; id: string };

	const app = getAppContext();
	const session = $derived(app.session!);
	const config = $derived(session.config);
	const daqDeviceId = $derived(config.daq.device);

	const params = useSearchParams(
		createSearchParamsSchema({
			nav: { type: 'string', default: 'channels' },
			id: { type: 'string', default: '' }
		}),
		{ pushHistory: false, noScroll: true }
	);

	const activeNav = $derived<NavTarget>(
		params.nav === 'device' && params.id
			? { type: 'device', id: params.id }
			: params.nav === 'profile' && params.id
				? { type: 'profile', id: params.id }
				: { type: 'channels' }
	);
</script>

{#if activeNav.type === 'channels'}
	<!-- Session info -->
	<section class="mb-6">
		<h3 class="mb-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">Session</h3>
		<div class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
			<span class="text-muted-foreground">Rig</span>
			<span class="text-foreground">{config.info.name}</span>

			<span class="text-muted-foreground">Devices</span>
			<span class="text-foreground">
				{[...session.devices.devices.values()].filter((d) => d.connected).length}/{session.devices.devices.size}
			</span>

			<span class="text-muted-foreground">Tiles</span>
			<span class="text-foreground">{session.tiles.length}</span>

			<span class="text-muted-foreground">Stacks</span>
			<span class="text-foreground">{session.stacks.length}</span>

			{#if session.sessionDir}
				<span class="text-muted-foreground">Directory</span>
				<span class="truncate text-foreground" title={session.sessionDir}>
					{session.sessionDir}
				</span>
			{/if}
		</div>
	</section>

	<!-- Channel cards -->
	<section>
		<h3 class="mb-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">Channels</h3>
		<div class="grid auto-rows-auto grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3">
			{#each Object.entries(config.channels) as [channelId, channel] (channelId)}
				<div class="rounded-lg border bg-card p-3 text-xs text-card-foreground shadow-sm">
					<div class="mb-2 flex items-center gap-2">
						{#if channel.emission}
							<span
								class="h-2.5 w-2.5 shrink-0 rounded-full"
								style="background-color: {wavelengthToColor(channel.emission)}"
							></span>
						{/if}
						<span class="font-medium text-foreground">
							{channel.label ?? sanitizeString(channelId)}
						</span>
					</div>
					<div class="space-y-1 text-muted-foreground">
						<div class="flex justify-between">
							<span>Detection</span>
							<span class="text-foreground">{channel.detection}</span>
						</div>
						<div class="flex justify-between">
							<span>Illumination</span>
							<span class="text-foreground">{channel.illumination}</span>
						</div>
						{#each Object.entries(channel.filters) as [fwId, position] (fwId)}
							<div class="flex justify-between">
								<span>{fwId}</span>
								<span class="text-foreground">{position}</span>
							</div>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	</section>
{:else if activeNav.type === 'profile' && activeNav.id}
	<ProfileConfig {session} profileId={activeNav.id} />
{:else if activeNav.type === 'device'}
	{#if activeNav.id in session.cameras}
		<CameraConfig {session} deviceId={activeNav.id} />
	{:else if activeNav.id in session.lasers}
		<LaserConfig {session} deviceId={activeNav.id} />
	{:else if activeNav.id === daqDeviceId}
		<DaqConfig {session} deviceId={activeNav.id} />
	{:else}
		<DeviceConfig {session} deviceId={activeNav.id} />
	{/if}
{/if}
