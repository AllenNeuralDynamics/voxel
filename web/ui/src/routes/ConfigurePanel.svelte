<script lang="ts">
	import type { Session } from '$lib/main';
	import { sanitizeString } from '$lib/utils';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	const config = $derived(session.config);
	const activeProfileId = $derived(session.activeProfileId);
	const activeProfile = $derived(activeProfileId ? config.profiles[activeProfileId] ?? null : null);
	const activeChannelIds = $derived(new Set(activeProfile?.channels ?? []));
	const stackOnlySet = $derived(new Set(activeProfile?.daq.stack_only ?? []));
</script>

<div class="flex h-full">
	<!-- Left Aside -->
	<aside class="w-52 shrink-0 space-y-6 overflow-auto border-r border-border p-4">
		<!-- Devices -->
		<section>
			<h3 class="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">Devices</h3>
			<div class="space-y-1">
				{#each [...session.devices.devices] as [id, device] (id)}
					<div class="flex items-center justify-between rounded px-2 py-1 text-xs">
						<span class="truncate text-foreground">{id}</span>
						<span
							class="h-2 w-2 shrink-0 rounded-full {device.connected
								? 'bg-success'
								: 'bg-muted-foreground/30'}"
							title={device.connected ? 'Connected' : 'Disconnected'}
						></span>
					</div>
				{/each}
			</div>
		</section>

		<!-- DAQ Ports -->
		<section>
			<h3 class="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
				DAQ Ports
				<span class="ml-1 font-normal normal-case text-muted-foreground/70">({config.daq.device})</span>
			</h3>
			<div class="space-y-1">
				{#each Object.entries(config.daq.acq_ports) as [deviceId, port] (deviceId)}
					<div class="flex items-center justify-between rounded px-2 py-1 text-xs">
						<span class="truncate text-foreground">{deviceId}</span>
						<span class="font-mono text-muted-foreground">{port}</span>
					</div>
				{/each}
			</div>
		</section>
	</aside>

	<!-- Main Section -->
	<div class="flex-1 space-y-6 overflow-auto p-6">
		<!-- Channels -->
		<section>
			<h3 class="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">Channels</h3>
			<div class="grid auto-rows-auto grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
				{#each Object.entries(config.channels) as [channelId, channel] (channelId)}
					{@const isActive = activeChannelIds.has(channelId)}
					<div
						class="rounded-lg border p-3 text-xs {isActive
							? 'border-foreground/50'
							: 'border-border opacity-50'}"
					>
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

		<!-- Active Profile -->
		{#if activeProfile && activeProfileId}
			<section>
				<h3 class="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
					Active Profile
				</h3>
				<div class="space-y-3">
					<div class="text-sm">
						<span class="font-medium text-foreground">
							{activeProfile.label ?? sanitizeString(activeProfileId)}
						</span>
						{#if activeProfile.desc}
							<span class="ml-2 text-muted-foreground">{activeProfile.desc}</span>
						{/if}
					</div>
					<div class="flex flex-wrap gap-1.5">
						{#each activeProfile.channels as chId (chId)}
							<span class="rounded-full bg-muted px-2 py-0.5 text-xs text-foreground">
								{config.channels[chId]?.label ?? sanitizeString(chId)}
							</span>
						{/each}
					</div>
				</div>
			</section>

			<!-- Timing -->
			<section>
				<h3 class="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">Timing</h3>
				<div class="grid grid-cols-3 gap-4 text-xs">
					<div>
						<span class="text-muted-foreground">Sample Rate</span>
						<div class="mt-0.5 font-medium text-foreground">{activeProfile.daq.timing.sample_rate}</div>
					</div>
					<div>
						<span class="text-muted-foreground">Duration</span>
						<div class="mt-0.5 font-medium text-foreground">{activeProfile.daq.timing.duration}</div>
					</div>
					<div>
						<span class="text-muted-foreground">Rest Time</span>
						<div class="mt-0.5 font-medium text-foreground">{activeProfile.daq.timing.rest_time}</div>
					</div>
				</div>
			</section>

			<!-- Waveforms -->
			<section>
				<h3 class="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">Waveforms</h3>
				<div class="grid auto-rows-auto grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
					{#each Object.entries(activeProfile.daq.waveforms) as [deviceId, waveform] (deviceId)}
						<div class="rounded-lg border border-border p-3 text-xs">
							<div class="mb-2 flex items-center justify-between">
								<span class="font-medium text-foreground">{deviceId}</span>
								{#if stackOnlySet.has(deviceId)}
									<span
										class="rounded bg-muted px-1.5 py-0.5 text-[0.6rem] uppercase text-muted-foreground"
									>
										stack
									</span>
								{/if}
							</div>
							<div class="space-y-1 text-muted-foreground">
								<div class="flex justify-between">
									<span>Type</span>
									<span class="text-foreground">{waveform.type}</span>
								</div>
								<div class="flex justify-between">
									<span>Voltage</span>
									<span class="text-foreground">
										{waveform.voltage.min}–{waveform.voltage.max} V
									</span>
								</div>
								<div class="flex justify-between">
									<span>Window</span>
									<span class="text-foreground">
										{waveform.window.min}–{waveform.window.max}
									</span>
								</div>
							</div>
						</div>
					{/each}
				</div>
			</section>
		{:else}
			<div class="flex items-center justify-center py-12">
				<p class="text-sm text-muted-foreground">No active profile selected</p>
			</div>
		{/if}
	</div>
</div>

<script lang="ts" module>
	/** Approximate visible color from emission wavelength (nm). */
	function wavelengthToColor(nm: number): string {
		if (nm < 380) return '#7f00ff';
		if (nm < 440) {
			const t = (nm - 380) / (440 - 380);
			return `rgb(${Math.round((1 - t) * 128)}, 0, ${Math.round(255 * t)})`;
		}
		if (nm < 490) {
			const t = (nm - 440) / (490 - 440);
			return `rgb(0, ${Math.round(255 * t)}, ${Math.round(255 * (1 - t))})`;
		}
		if (nm < 510) {
			const t = (nm - 490) / (510 - 490);
			return `rgb(0, 255, ${Math.round(255 * (1 - t))})`;
		}
		if (nm < 580) {
			const t = (nm - 510) / (580 - 510);
			return `rgb(${Math.round(255 * t)}, 255, 0)`;
		}
		if (nm < 645) {
			const t = (nm - 580) / (645 - 580);
			return `rgb(255, ${Math.round(255 * (1 - t))}, 0)`;
		}
		if (nm <= 780) return '#ff0000';
		return '#7f0000';
	}
</script>
