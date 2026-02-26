<script lang="ts">
	import type { Session } from '$lib/main';
	import { sanitizeString, wavelengthToColor } from '$lib/utils';
	import { Select } from '$lib/ui/primitives';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	const config = $derived(session.config);
	const activeProfileId = $derived(session.activeProfileId);

	let selectedProfileId = $state('');
	const profileOptions = $derived(
		Object.entries(config.profiles).map(([id, p]) => ({
			value: id,
			label: p.label ?? sanitizeString(id),
			description: p.desc
		}))
	);

	$effect(() => {
		if (!selectedProfileId && activeProfileId) {
			selectedProfileId = activeProfileId;
		}
	});

	const selectedProfile = $derived(
		selectedProfileId ? (config.profiles[selectedProfileId] ?? null) : null
	);
	const stackOnlySet = $derived(new Set(selectedProfile?.daq.stack_only ?? []));

	/** Collect unique device IDs from the profile's channels (detection, illumination, filters). */
	const profileDeviceIds = $derived.by(() => {
		if (!selectedProfile) return [];
		const ids = new Set<string>();
		for (const chId of selectedProfile.channels) {
			const ch = config.channels[chId];
			if (!ch) continue;
			ids.add(ch.detection);
			ids.add(ch.illumination);
			for (const fwId of Object.keys(ch.filters)) ids.add(fwId);
		}
		// Include waveform-only devices not already covered by channels
		for (const devId of Object.keys(selectedProfile.daq.waveforms)) ids.add(devId);
		return [...ids];
	});
</script>

<section class="space-y-6">
	<!-- Channels -->
	<section>
		<h3 class="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
			Channels
		</h3>
		<div class="grid auto-rows-auto grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
			{#each Object.entries(config.channels) as [channelId, channel] (channelId)}
				<div class="rounded-lg border bg-card text-card-foreground shadow-sm p-3 text-xs">
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

	<!-- Profile -->
	<section>
		<div class="flex flex-wrap items-center gap-2">
			<h3 class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Profile</h3>
			<Select
				bind:value={selectedProfileId}
				options={profileOptions}
				placeholder="Select profile..."
				size="sm"
				class="w-48"
			/>
			{#if selectedProfileId === activeProfileId}
				<span class="rounded-full bg-success/15 px-2 py-0.5 text-[0.65rem] font-medium text-success">
					Active
				</span>
			{/if}
			{#if selectedProfile}
				{#each selectedProfile.channels as chId (chId)}
					<span class="rounded-full bg-muted px-2 py-0.5 text-xs text-foreground">
						{config.channels[chId]?.label ?? sanitizeString(chId)}
					</span>
				{/each}
			{/if}
		</div>
	</section>

	{#if selectedProfile}
		<!-- Frame Timing -->
		<section>
			<h3 class="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
				Frame Timing
			</h3>
			<div class="grid grid-cols-3 gap-4 text-xs">
				<div>
					<span class="text-muted-foreground">Sample Rate</span>
					<div class="mt-0.5 font-medium text-foreground">
						{selectedProfile.daq.timing.sample_rate}
					</div>
				</div>
				<div>
					<span class="text-muted-foreground">Duration</span>
					<div class="mt-0.5 font-medium text-foreground">
						{selectedProfile.daq.timing.duration}
					</div>
				</div>
				<div>
					<span class="text-muted-foreground">Rest Time</span>
					<div class="mt-0.5 font-medium text-foreground">
						{selectedProfile.daq.timing.rest_time}
					</div>
				</div>
			</div>
		</section>

		<!-- Devices -->
		<section>
			<h3 class="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
				Devices
			</h3>
			<div class="grid auto-rows-auto grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3">
				{#each profileDeviceIds as deviceId (deviceId)}
					{@const waveform = selectedProfile.daq.waveforms[deviceId]}
					<div class="rounded-lg border bg-card text-card-foreground shadow-sm p-4 text-xs">
						<!-- Header -->
						<div class="mb-3 flex items-center justify-between">
							<span class="text-sm font-medium text-foreground">{sanitizeString(deviceId)}</span>
							{#if stackOnlySet.has(deviceId)}
								<span class="rounded bg-muted px-1.5 py-0.5 text-[0.6rem] uppercase text-muted-foreground">
									stack
								</span>
							{/if}
						</div>

						<!-- Waveform -->
						{#if waveform}
							<div class="mb-3">
								<h4 class="mb-1.5 text-[0.65rem] font-medium uppercase tracking-wide text-muted-foreground">
									Waveform
								</h4>
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
						{/if}

						<!-- Settings (placeholder) -->
						<div>
							<h4 class="mb-1.5 text-[0.65rem] font-medium uppercase tracking-wide text-muted-foreground">
								Settings
							</h4>
							<p class="text-muted-foreground/60">—</p>
						</div>
					</div>
				{/each}
			</div>
		</section>
	{:else}
		<div class="flex items-center justify-center py-12">
			<p class="text-sm text-muted-foreground">Select a profile to view details</p>
		</div>
	{/if}
</section>
