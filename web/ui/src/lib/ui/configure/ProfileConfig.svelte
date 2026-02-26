<script lang="ts">
	import type { Session } from '$lib/main';
	import { sanitizeString } from '$lib/utils';
	import { Button } from '$lib/ui/primitives';
	import { Collapsible } from 'bits-ui';
	import { ChevronRight } from '$lib/icons';
	import { WaveformPlot } from '$lib/ui/waveform';

	interface Props {
		session: Session;
		profileId: string;
	}

	let { session, profileId }: Props = $props();

	const config = $derived(session.config);
	const activeProfileId = $derived(session.activeProfileId);
	const isActive = $derived(profileId === activeProfileId);
	const profile = $derived(config.profiles[profileId]);
	const stackOnlySet = $derived(new Set(profile?.daq.stack_only ?? []));

	/** Unique device IDs from the profile's channels + waveform-only devices. */
	const profileDeviceIds = $derived.by(() => {
		if (!profile) return [];
		const ids = new Set<string>();
		for (const chId of profile.channels) {
			const ch = config.channels[chId];
			if (!ch) continue;
			ids.add(ch.detection);
			ids.add(ch.illumination);
			for (const fwId of Object.keys(ch.filters)) ids.add(fwId);
		}
		for (const devId of Object.keys(profile.daq.waveforms)) ids.add(devId);
		return [...ids];
	});

	const waveformDeviceIds = $derived(profile ? Object.keys(profile.daq.waveforms) : []);
	const duration = $derived(Number(profile?.daq.timing.duration ?? 0));
	const restTime = $derived(Number(profile?.daq.timing.rest_time ?? 0));

	const traceColors: string[] = [
		'#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6',
		'#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1'
	];

	const waveformColors = $derived.by(() => {
		const map: Record<string, string> = {};
		waveformDeviceIds.forEach((id, i) => {
			map[id] = traceColors[i % traceColors.length];
		});
		return map;
	});

	let expandedDevices = $state(new Set<string>());
</script>

{#if profile}
	<section class="space-y-6">
		<!-- Header -->
		<div>
			<div class="flex items-center gap-1.5">
				<h2 class="text-sm font-medium text-foreground">
					{profile.label ?? sanitizeString(profileId)}
				</h2>
				<div class="ml-auto flex items-center gap-1.5">
					{#each profile.channels as chId (chId)}
						<span class="rounded-full bg-muted px-1.5 py-px text-[0.65rem] text-foreground">
							{config.channels[chId]?.label ?? sanitizeString(chId)}
						</span>
					{/each}
					{#if isActive}
						<span class="inline-flex h-6 items-center justify-center rounded-full bg-success/15 px-3.5 text-[0.65rem] font-medium text-success">
							Active
						</span>
					{:else}
						<Button
							size="xs"
							variant="outline"
							class="rounded-full"
							onclick={() => session.activateProfile(profileId)}
							disabled={session.isMutating}
						>
							Activate
						</Button>
					{/if}
				</div>
			</div>
			{#if profile.desc}
				<p class="mt-1 text-xs text-muted-foreground">{profile.desc}</p>
			{/if}
		</div>

		<!-- Settings -->
		<section>
			<h3 class="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
				Settings
			</h3>
			<div class="space-y-0.5">
				{#each profileDeviceIds as deviceId (deviceId)}
					<Collapsible.Root
						open={expandedDevices.has(deviceId)}
						onOpenChange={(open) => {
							const next = new Set(expandedDevices);
							if (open) next.add(deviceId);
							else next.delete(deviceId);
							expandedDevices = next;
						}}
					>
						<Collapsible.Trigger
							class="-ml-2 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors hover:bg-muted"
						>
							<ChevronRight
								width="14"
								height="14"
								class="shrink-0 text-muted-foreground transition-transform {expandedDevices.has(deviceId) ? 'rotate-90' : ''}"
							/>
							<span class="font-medium text-foreground">{sanitizeString(deviceId)}</span>
						</Collapsible.Trigger>
						<Collapsible.Content class="pb-2 pl-7 pr-2 pt-1">
							<p class="text-xs text-muted-foreground/60">Coming soon</p>
						</Collapsible.Content>
					</Collapsible.Root>
				{/each}
			</div>
		</section>

		<!-- Waveforms -->
		<section>
			<h3 class="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
				Waveforms
			</h3>

			<!-- Frame Timing -->
			<div class="mb-4 grid grid-cols-3 gap-4 text-xs">
				<div>
					<span class="text-muted-foreground">Sample Rate</span>
					<div class="mt-0.5 font-medium text-foreground">
						{profile.daq.timing.sample_rate}
					</div>
				</div>
				<div>
					<span class="text-muted-foreground">Duration</span>
					<div class="mt-0.5 font-medium text-foreground">
						{profile.daq.timing.duration}
					</div>
				</div>
				<div>
					<span class="text-muted-foreground">Rest Time</span>
					<div class="mt-0.5 font-medium text-foreground">
						{profile.daq.timing.rest_time}
					</div>
				</div>
			</div>

			<!-- SVG Plot -->
			{#if waveformDeviceIds.length > 0 && duration > 0}
				<div class="mb-4 rounded-lg border bg-card p-3 shadow-sm">
					<WaveformPlot
						waveforms={profile.daq.waveforms}
						{duration}
						{restTime}
						colors={waveformColors}
					/>
				</div>
			{/if}

			<!-- Per-device waveform details -->
			<div class="divide-y divide-border rounded-lg border">
				{#each waveformDeviceIds as deviceId (deviceId)}
					{@const waveform = profile.daq.waveforms[deviceId]}
					<div class="flex items-center gap-3 px-3 py-2 text-xs">
						<span
							class="h-2 w-2 shrink-0 rounded-full"
							style="background-color: {waveformColors[deviceId]}"
						></span>
						<span class="w-28 font-medium text-foreground">{sanitizeString(deviceId)}</span>
						<span class="text-muted-foreground">{waveform.type}</span>
						<span class="text-muted-foreground">
							{waveform.voltage.min}–{waveform.voltage.max} V
						</span>
						<span class="text-muted-foreground">
							[{waveform.window.min}–{waveform.window.max}]
						</span>
						{#if stackOnlySet.has(deviceId)}
							<span class="rounded bg-muted px-1.5 py-0.5 text-[0.6rem] uppercase text-muted-foreground">
								stack
							</span>
						{/if}
					</div>
				{/each}
			</div>
		</section>
	</section>
{/if}
