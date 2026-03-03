<script lang="ts">
	import { untrack } from 'svelte';
	import type { Session } from '$lib/main';
	import { sanitizeString } from '$lib/utils';
	import { Collapsible } from 'bits-ui';
	import { SvelteMap, SvelteSet } from 'svelte/reactivity';
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

	type DeviceRole = 'camera' | 'laser' | 'filter' | 'aux' | 'waveform';
	const ROLE_ORDER: Record<DeviceRole, number> = { camera: 0, laser: 1, filter: 2, aux: 3, waveform: 4 };

	/** Unique device IDs from the profile's channels + aux devices + waveform-only devices, sorted by role. */
	const profileDeviceIds = $derived.by(() => {
		if (!profile) return [];
		const roles = new SvelteMap<string, DeviceRole>();
		for (const chId of profile.channels) {
			const ch = config.channels[chId];
			if (!ch) continue;
			if (!roles.has(ch.detection)) roles.set(ch.detection, 'camera');
			if (!roles.has(ch.illumination)) roles.set(ch.illumination, 'laser');
			for (const fwId of Object.keys(ch.filters)) {
				if (!roles.has(fwId)) roles.set(fwId, 'filter');
			}
			// Aux devices from detection/illumination optical paths
			const detPath = config.detection[ch.detection];
			if (detPath) {
				for (const auxId of detPath.aux_devices) {
					if (!roles.has(auxId)) roles.set(auxId, 'aux');
				}
			}
			const illPath = config.illumination[ch.illumination];
			if (illPath) {
				for (const auxId of illPath.aux_devices) {
					if (!roles.has(auxId)) roles.set(auxId, 'aux');
				}
			}
		}
		for (const devId of Object.keys(profile.daq.waveforms)) {
			if (!roles.has(devId)) roles.set(devId, 'waveform');
		}
		return [...roles.keys()].sort((a, b) => ROLE_ORDER[roles.get(a)!] - ROLE_ORDER[roles.get(b)!]);
	});

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
			<div class="rounded border bg-card shadow-sm">
				<div class="flex items-center justify-center gap-2 px-3 py-2">
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
				<div class="border-y px-4 py-2">
					{#if waveformDeviceIds.length > 0 && duration > 0}
						<WaveformPlot waveforms={sortedWaveforms} {duration} {restTime} {layerVisibility} colors={waveformColors} />
					{/if}
				</div>
				<div class="flex items-center justify-center gap-2 px-3 py-2">
					<SpinBox
						value={sampleRate}
						prefix="Sample Rate"
						suffix=" Hz"
						size="sm"
						appearance="full"
						numCharacters={7}
						align="right"
					/>
					<SpinBox
						value={duration}
						prefix="Duration"
						suffix=" s"
						size="sm"
						appearance="full"
						decimals={4}
						numCharacters={7}
						align="right"
					/>
					<SpinBox
						value={restTime}
						prefix="Rest Time"
						suffix=" s"
						size="sm"
						appearance="full"
						decimals={4}
						numCharacters={8}
						align="right"
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
