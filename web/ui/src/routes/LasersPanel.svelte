<script lang="ts">
	import { POWER_HISTORY_MAX, type Session, type Laser } from '$lib/main';
	import type { ChannelConfig } from '$lib/main/types';
	import Switch from '$lib/ui/kit/Switch.svelte';
	import SpinBox from '$lib/ui/kit/SpinBox.svelte';
	import Slider from '$lib/ui/kit/Slider.svelte';
	import { InformationOutline, Power } from '$lib/icons';
	import { Popover } from 'bits-ui';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	const allLasers = $derived(Object.values(session.lasers));

	// Record power history on all lasers
	$effect(() => {
		const interval = setInterval(() => {
			for (const laser of allLasers) {
				laser.recordPower();
			}
		}, 100);
		return () => clearInterval(interval);
	});

	const profileLasers = $derived(allLasers.filter((l) => session.getChannelFor(l.deviceId)));
	const otherLasers = $derived(allLasers.filter((l) => !session.getChannelFor(l.deviceId)));

	const activeProfileLabel = $derived.by(() => {
		const p = session.activeProfileConfig;
		return p ? (p.label ?? session.activeProfileId) : 'None';
	});

	const anyLaserEnabled = $derived(allLasers.some((l) => l.isEnabled));
	const anyHistory = $derived(allLasers.some((l) => l.hasHistory));
	const globalMaxPower = $derived(Math.max(...allLasers.map((l) => l.maxPower)));

	let _selectedDeviceId = $state('');

	const selectedLaser = $derived(allLasers.find((l) => l.deviceId === _selectedDeviceId) ?? allLasers[0] ?? null);
	const selectedDeviceId = $derived(selectedLaser?.deviceId ?? '');

	function selectRow(deviceId: string) {
		_selectedDeviceId = deviceId;
	}

	function stopAllLasers() {
		for (const laser of allLasers) {
			if (laser.isEnabled) laser.disable();
		}
	}
</script>

{#snippet laserRow(laser: Laser)}
	<button
		onclick={() => selectRow(laser.deviceId)}
		class="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors
			{selectedDeviceId === laser.deviceId ? 'bg-muted' : 'bg-muted/50 hover:bg-muted/80'}"
	>
		<!-- Wavelength dot + label -->
		<div class="flex w-20 shrink-0 items-center gap-2">
			<div class="h-2.5 w-2.5 rounded-full" style="background-color: {laser.color};"></div>
			<span class="text-xs font-medium tabular-nums">
				{laser.wavelength ? `${laser.wavelength} nm` : 'Laser'}
			</span>
		</div>

		<!-- Power slider -->
		<div class="flex min-w-32 flex-1 items-center">
			{#if typeof laser.powerSetpoint === 'number'}
				<Slider
					target={laser.powerSetpoint}
					value={laser.powerMw}
					min={0}
					max={laser.maxPower}
					step={1}
					throttle={100}
					onChange={(v) => laser.setPower(v)}
				/>
			{/if}
		</div>

		<!-- Actual power readout -->
		<div class="w-16 shrink-0 text-right font-mono text-xs text-muted-foreground tabular-nums">
			{#if typeof laser.powerMw === 'number'}
				{laser.powerMw.toFixed(1)} mW
			{/if}
		</div>

		<!-- Toggle -->
		<div class="shrink-0">
			<Switch checked={laser.isEnabled} onCheckedChange={() => laser.toggle()} />
		</div>
	</button>
{/snippet}

{#snippet channelInfoPopover(cfg: ChannelConfig)}
	<Popover.Root>
		<Popover.Trigger class="flex items-center gap-1.5 rounded px-1 py-0.5 transition-colors hover:bg-accent">
			<span class="font-medium text-foreground">{cfg.label}</span>
			<InformationOutline width="14" height="14" class="text-muted-foreground" />
		</Popover.Trigger>
		<Popover.Content
			class="z-50 w-64 rounded border border-zinc-700 bg-zinc-900 p-3 text-left text-xs text-zinc-200 shadow-xl outline-none"
			sideOffset={4}
			side="top"
			align="end"
		>
			<div class="space-y-2">
				<div>
					{#if cfg.desc}
						<p class="mt-1 text-xs text-zinc-300">{cfg.desc}</p>
					{/if}
				</div>
				<div class="space-y-1 border-t border-zinc-800 pt-2 text-[0.7rem] text-zinc-300">
					{#if cfg.emission}
						<div class="flex justify-between gap-2">
							<span class="text-zinc-400">Emission</span>
							<span class="text-right text-zinc-200">{cfg.emission} nm</span>
						</div>
					{/if}
					{#if cfg.detection}
						<div class="flex justify-between gap-2">
							<span class="text-zinc-400">Detection</span>
							<span class="text-right text-zinc-200">{cfg.detection}</span>
						</div>
					{/if}
					{#if Object.keys(cfg.filters).length > 0}
						<div class="space-y-1">
							<div class="mb-1 border-b border-zinc-800 pt-1 text-zinc-500/90">Filters</div>
							{#each Object.entries(cfg.filters) as [wheelId, position] (position)}
								<div class="flex justify-between gap-2">
									<span class="text-zinc-400">{wheelId}:</span>
									<span class="text-right text-zinc-200">{position}</span>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>
		</Popover.Content>
	</Popover.Root>
{/snippet}

{#snippet detailPanel(laser: Laser, cfg: ChannelConfig | null)}
	<div class="flex h-full w-96 shrink-0 flex-col border-r border-border bg-card">
		<!-- Header -->
		<div class="flex items-center justify-between px-4 pt-4">
			<div class="flex items-center gap-2">
				<div class="h-3 w-3 rounded-full" style="background-color: {laser.color};"></div>
				<span class="text-sm font-medium">
					{laser.wavelength ? `${laser.wavelength} nm` : 'Laser'}
				</span>
			</div>
			<span class="text-[0.65rem] text-muted-foreground">{laser.deviceId}</span>
		</div>

		<!-- Power setpoint + quick actions -->
		{#if typeof laser.powerSetpoint === 'number'}
			<div class="space-y-2 px-4 pt-4">
				<div>
					<h5 class="mb-1.5 text-[0.6rem] font-medium text-muted-foreground uppercase">Power Setpoint</h5>
					<SpinBox
						value={laser.powerSetpoint}
						min={0}
						max={laser.maxPower}
						step={1}
						decimals={1}
						suffix="mW"
						size="sm"
						class="w-full"
						onChange={(v) => laser.setPower(v)}
					/>
				</div>
				<div class="flex gap-1.5">
					{#each [0, 25, 50, 75, 100] as pct (pct)}
						{@const targetValue = (laser.maxPower * pct) / 100}
						<button
							onclick={() => laser.setPower(targetValue)}
							class="flex-1 rounded border border-border px-1 py-1 text-[0.65rem] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
						>
							{pct}%
						</button>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Power history sparkline (all lasers) — fills remaining space -->
		<div class="flex max-h-40 min-h-16 flex-1 flex-col px-4 pt-4">
			<div class="mb-1.5 flex items-baseline justify-between">
				<h5 class="text-[0.6rem] font-medium text-muted-foreground uppercase">Power</h5>
				<span class="font-mono text-xs text-foreground tabular-nums">
					{typeof laser.powerMw === 'number' ? `${laser.powerMw.toFixed(1)} mW` : '—'}
				</span>
			</div>
			<div class="min-h-16 flex-1 rounded border border-border bg-muted/30">
				{#if anyHistory}
					<svg viewBox="0 0 {POWER_HISTORY_MAX} 100" preserveAspectRatio="none" class="h-full w-full">
						{#each allLasers as l (l.deviceId)}
							{@const isSelected = l.deviceId === laser.deviceId}
							{#if l.hasHistory}
								<polyline
									points={l.powerHistory
										.map(
											(v, i) =>
												`${((i / (POWER_HISTORY_MAX - 1)) * POWER_HISTORY_MAX).toFixed(1)},${(100 - (v / globalMaxPower) * 100).toFixed(1)}`
										)
										.join(' ')}
									fill="none"
									stroke={l.color}
									stroke-width={isSelected ? 2 : 1.5}
									opacity={isSelected ? 0.75 : 0.5}
									vector-effect="non-scaling-stroke"
								/>
							{/if}
						{/each}
					</svg>
				{:else}
					<div class="flex h-full items-center justify-center">
						<span class="text-[0.6rem] text-muted-foreground/50">Collecting data...</span>
					</div>
				{/if}
			</div>
		</div>

		<!-- Footer: temperature + channel info -->
		<div class="mt-auto flex items-center justify-between border-t border-border px-4 py-2 text-xs">
			<span class="font-mono text-muted-foreground tabular-nums">
				{typeof laser.temperatureC === 'number' ? `${laser.temperatureC.toFixed(1)}°C` : ''}
			</span>
			{#if cfg}
				{@render channelInfoPopover(cfg)}
			{/if}
		</div>
	</div>
{/snippet}

{#if allLasers.length === 0}
	<div class="flex h-full items-center justify-center">
		<p class="text-xs text-muted-foreground">No lasers configured</p>
	</div>
{:else if selectedLaser}
	<div class="flex h-full">
		<!-- Left: detail panel -->
		{@render detailPanel(selectedLaser, session.getChannelFor(selectedLaser.deviceId)?.config ?? null)}

		<!-- Right: laser list -->
		<div class="flex flex-1 flex-col overflow-auto px-4">
			<div class="flex h-full flex-col gap-3">
				{#if profileLasers.length > 0}
					<div>
						<div class="flex items-center justify-between py-3">
							<h4 class="text-[0.65rem] font-medium text-muted-foreground/60 uppercase">
								Active Profile <span class="pl-2 text-muted-foreground">{activeProfileLabel}</span>
							</h4>
							<button
								onclick={stopAllLasers}
								class="flex items-center gap-1.5 rounded bg-danger/20 px-2 py-1 text-xs text-danger transition-all hover:bg-danger/30 {anyLaserEnabled
									? ''
									: 'pointer-events-none opacity-0'}"
							>
								<Power width="14" height="14" />
								<span>Stop All</span>
							</button>
						</div>
						<div class="space-y-2">
							{#each profileLasers as laser (laser.deviceId)}
								{@render laserRow(laser)}
							{/each}
						</div>
					</div>
				{/if}

				{#if otherLasers.length > 0}
					<div>
						<h4 class="mb-1 text-[0.65rem] font-medium text-muted-foreground/60 uppercase">Other Lasers</h4>
						<div class="space-y-2">
							{#each otherLasers as laser (laser.deviceId)}
								{@render laserRow(laser)}
							{/each}
						</div>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}
