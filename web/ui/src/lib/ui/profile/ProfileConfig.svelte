<script lang="ts">
	import { untrack } from 'svelte';
	import type { Session } from '$lib/main';
	import { sanitizeString } from '$lib/utils';
	import { Collapsible } from 'bits-ui';
	import { SvelteSet } from 'svelte/reactivity';
	import { ChevronRight } from '$lib/icons';
	import { WaveformPlot } from '$lib/ui/waveform';
	import { SpinBox } from '$lib/ui/kit';
	import { ProfileChips, ProfileStatus } from '$lib/ui/profile';

	interface Props {
		session: Session;
		profileId: string;
	}

	let { session, profileId }: Props = $props();

	const config = $derived(session.config);
	const profile = $derived(config.profiles[profileId]);
	const stackOnlySet = $derived(new SvelteSet(profile?.daq.stack_only ?? []));

	/** Unique device IDs from the profile, sorted by role via ProfileDevices. */
	const profileDeviceIds = $derived(session.profileDevices.discover(profileId).map((d) => d.id));

	/** Waveform device IDs in role-sorted order (subset of profileDeviceIds). */
	const waveformDeviceIds = $derived(profileDeviceIds.filter((id) => profile?.daq.waveforms[id] != null));

	/** Waveforms record matching the sorted device order. */
	const sortedWaveforms = $derived.by(() => {
		if (!profile) return {};
		const sorted: Record<string, (typeof profile.daq.waveforms)[string]> = {};
		for (const id of waveformDeviceIds) sorted[id] = profile.daq.waveforms[id];
		return sorted;
	});

	const duration = $derived(Number(profile?.daq.timing.duration ?? 0));
	const restTime = $derived(Number(profile?.daq.timing.rest_time ?? 0));
	const sampleRate = $derived(Number(profile?.daq.timing.sample_rate ?? 0));
	const frequency = $derived(duration + restTime > 0 ? 1 / (duration + restTime) : 0);
	const samples = $derived(Math.floor(sampleRate * duration));

	const formatFrequency = (hz: number) => {
		if (hz >= 1_000_000) return `${(hz / 1_000_000).toFixed(2)} MHz`;
		if (hz >= 1_000) return `${(hz / 1_000).toFixed(2)} kHz`;
		return `${hz.toFixed(2)} Hz`;
	};

	const traceColors: string[] = [
		'#10b981',
		'#3b82f6',
		'#f59e0b',
		'#ef4444',
		'#8b5cf6',
		'#ec4899',
		'#06b6d4',
		'#84cc16',
		'#f97316',
		'#6366f1'
	];

	const waveformColors = $derived.by(() => {
		const map: Record<string, string> = {};
		waveformDeviceIds.forEach((id, i) => {
			map[id] = traceColors[i % traceColors.length];
		});
		return map;
	});

	let expandedDevices = $state(new Set<string>());

	let layerVisibility = $state<Record<string, boolean>>({});

	$effect(() => {
		const keys = waveformDeviceIds;
		untrack(() => {
			const next: Record<string, boolean> = {};
			for (const k of keys) next[k] = layerVisibility[k] ?? true;
			layerVisibility = next;
		});
	});

	function toggleLayer(deviceId: string) {
		layerVisibility = { ...layerVisibility, [deviceId]: !layerVisibility[deviceId] };
	}
</script>

{#if profile}
	<section class="space-y-6">
		<!-- Header -->
		<div>
			<div class="flex items-center gap-1.5">
				<h2 class="text-sm font-medium text-foreground">
					{profile.label ?? sanitizeString(profileId)}
				</h2>
				<ProfileChips {session} {profileId} class="ml-auto" />
				<ProfileStatus {session} {profileId} />
			</div>
			{#if profile.desc}
				<p class="mt-1 text-xs text-muted-foreground">{profile.desc}</p>
			{/if}
		</div>

		<!-- Waveforms -->
		<section>
			<div class="grid grid-cols-[minmax(0,1fr)_auto] grid-rows-[1fr_auto] rounded border bg-card shadow-sm">
				<!-- Plot: row 1, col 1 -->
				<div class="px-4 py-2">
					{#if waveformDeviceIds.length > 0 && duration > 0}
						<WaveformPlot waveforms={sortedWaveforms} {duration} {restTime} {layerVisibility} colors={waveformColors} />
					{/if}
				</div>

				<!-- Timing controls: row 1, col 2 -->
				<div class="flex flex-col justify-between border-l">
					<div class="space-y-1.5 px-3 py-3">
						<SpinBox
							value={sampleRate}
							prefix="Rate"
							suffix=" Hz"
							size="sm"
							appearance="full"
							numCharacters={10}
							align="right"
						/>
						<SpinBox
							value={duration}
							prefix="Duration"
							suffix=" s"
							size="sm"
							appearance="full"
							decimals={4}
							numCharacters={10}
							align="right"
						/>
						<SpinBox
							value={restTime}
							prefix="Rest"
							suffix=" s"
							size="sm"
							appearance="full"
							decimals={4}
							numCharacters={10}
							align="right"
						/>
					</div>

					<div class="space-y-1 border-t px-3 py-2 text-[0.65rem] text-muted-foreground">
						<div class="flex justify-between">
							<span>Frequency</span>
							<span class="font-mono text-foreground">{formatFrequency(frequency)}</span>
						</div>
						<div class="flex justify-between">
							<span>Samples</span>
							<span class="font-mono text-foreground">{samples.toLocaleString()}</span>
						</div>
					</div>
				</div>

				<!-- Layer toggles: row 2, col 1 -->
				<div class="flex flex-wrap items-center gap-1.5 border-t px-3 py-2">
					{#each waveformDeviceIds as deviceId (deviceId)}
						{@const visible = layerVisibility[deviceId] !== false}
						<button
							type="button"
							class="flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.6rem] transition-colors hover:bg-muted"
							onclick={() => toggleLayer(deviceId)}
						>
							<span
								class="inline-block h-2 w-2 shrink-0 rounded-full {visible ? '' : 'opacity-30'}"
								style="background-color: {waveformColors[deviceId]}"
							></span>
							<span class={visible ? 'text-foreground' : 'text-muted-foreground/50'}>{deviceId}</span>
						</button>
					{/each}
				</div>

				<!-- Cycles: row 2, col 2 -->
				<div class="border-t border-l px-3 py-2">
					<SpinBox
						value={1}
						prefix="Cycles"
						min={1}
						max={4}
						step={1}
						size="sm"
						appearance="full"
						numCharacters={1}
						disabled
					/>
				</div>
			</div>
		</section>

		<!-- Devices -->
		<section>
			<h3 class="mb-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">Devices</h3>
			<div class="space-y-0.5">
				{#each profileDeviceIds as deviceId (deviceId)}
					{@const waveform = profile.daq.waveforms[deviceId] ?? null}
					<Collapsible.Root
						open={expandedDevices.has(deviceId)}
						onOpenChange={(open) => {
							const next = new SvelteSet(expandedDevices);
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
								class="shrink-0 text-muted-foreground transition-transform {expandedDevices.has(deviceId)
									? 'rotate-90'
									: ''}"
							/>
							<span class="font-medium text-foreground">{sanitizeString(deviceId)}</span>
							{#if waveform}
								<span class="text-muted-foreground">{waveform.type}</span>
								<span class="text-muted-foreground">
									{waveform.voltage.min}–{waveform.voltage.max} V
								</span>
								<span class="text-muted-foreground">
									[{waveform.window.min}–{waveform.window.max}]
								</span>
								{#if stackOnlySet.has(deviceId)}
									<span class="rounded bg-muted px-1.5 py-0.5 text-[0.6rem] text-muted-foreground uppercase">stack</span
									>
								{/if}
								<span class="ml-auto h-2 w-2 shrink-0 rounded-full" style="background-color: {waveformColors[deviceId]}"
								></span>
							{/if}
						</Collapsible.Trigger>
						<Collapsible.Content class="pt-1 pr-2 pb-2 pl-7">
							<p class="text-xs text-muted-foreground/60">Coming soon</p>
						</Collapsible.Content>
					</Collapsible.Root>
				{/each}
			</div>
		</section>
	</section>
{/if}
