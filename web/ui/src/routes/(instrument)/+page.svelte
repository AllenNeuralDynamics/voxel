<script lang="ts">
	import { getSessionContext } from '$lib/context';
	import { sanitizeString, wavelengthToColor } from '$lib/utils';

	const session = getSessionContext();
	const config = $derived(session.config);
</script>

<!-- Session info -->
<section class="mb-6">
	<h3 class="text-fg-muted mb-3 text-xs font-medium tracking-wide uppercase">Session</h3>
	<div class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
		<span class="text-fg-muted">Rig</span>
		<span class="text-fg">{config.info.name}</span>

		<span class="text-fg-muted">Devices</span>
		<span class="text-fg">
			{[...session.devices.devices.values()].filter((d) => d.connected).length}/{session.devices.devices.size}
		</span>

		<span class="text-fg-muted">Tiles</span>
		<span class="text-fg">{session.tiles.length}</span>

		<span class="text-fg-muted">Stacks</span>
		<span class="text-fg">{session.stacks.length}</span>

		{#if session.info?.session_dir}
			<span class="text-fg-muted">Directory</span>
			<span class="text-fg truncate" title={session.info.session_dir}>
				{session.info.session_dir}
			</span>
		{/if}
	</div>
</section>

<!-- Channel cards -->
<section>
	<h3 class="text-fg-muted mb-3 text-xs font-medium tracking-wide uppercase">Channels</h3>
	<div class="grid auto-rows-auto grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3">
		{#each Object.entries(config.channels) as [channelId, channel] (channelId)}
			<div class="text-fg rounded-lg border bg-card p-3 text-xs shadow-sm">
				<div class="mb-2 flex items-center gap-2">
					{#if channel.emission}
						<span
							class="h-2.5 w-2.5 shrink-0 rounded-full"
							style="background-color: {wavelengthToColor(channel.emission)}"
						></span>
					{/if}
					<span class="text-fg font-medium">
						{channel.label ?? sanitizeString(channelId)}
					</span>
				</div>
				<div class="text-fg-muted space-y-1">
					<div class="flex justify-between">
						<span>Detection</span>
						<span class="text-fg">{channel.detection}</span>
					</div>
					<div class="flex justify-between">
						<span>Illumination</span>
						<span class="text-fg">{channel.illumination}</span>
					</div>
					{#each Object.entries(channel.filters) as [fwId, position] (fwId)}
						<div class="flex justify-between">
							<span>{fwId}</span>
							<span class="text-fg">{position}</span>
						</div>
					{/each}
				</div>
			</div>
		{/each}
	</div>
</section>
