<script lang="ts">
	import { POWER_HISTORY_MAX, getChannelFor, type Session, type Laser } from '$lib/main';
	import type { ChannelConfig } from '$lib/main/types';
	import Switch from '$lib/ui/kit/Switch.svelte';
	import SpinBox from '$lib/ui/kit/SpinBox.svelte';
	import Slider from '$lib/ui/kit/Slider.svelte';
	import { InformationOutline, Power } from '$lib/icons';
	import { Popover } from 'bits-ui';
	import { useInterval } from 'runed';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	const allLasers = $derived(Object.values(session.lasers));

	// Record power history on all lasers
	useInterval(100, {
		callback: () => {
			for (const laser of allLasers) {
				laser.recordPower();
			}
		}
	});

	const profileLasers = $derived(
		session.activeProfileId
			? allLasers.filter((l) => getChannelFor(session.config, session.activeProfileId!, l.deviceId))
			: []
	);
	const otherLasers = $derived(
		session.activeProfileId
			? allLasers.filter((l) => !getChannelFor(session.config, session.activeProfileId!, l.deviceId))
			: allLasers
	);

	const activeProfileLabel = $derived.by(() => {
		const id = session.activeProfileId;
		const p = id ? (session.config.profiles[id] ?? null) : null;
		return p ? (p.label ?? id) : 'None';
	});

	const anyLaserEnabled = $derived(allLasers.some((l) => l.isEnabled));
	const anyHistory = $derived(allLasers.some((l) => l.hasHistory));
	const globalMaxPower = $derived(Math.max(...allLasers.map((l) => l.maxPower)));
	const currentMaxPower = $derived(Math.max(0, ...allLasers.map((l) => l.powerMw ?? 0)));

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
			{selectedDeviceId === laser.deviceId ? 'bg-element-selected' : 'hover:bg-element-hover bg-surface'}"
	>
		<!-- Wavelength dot + label -->
		<div class="flex w-20 shrink-0 items-center gap-2">
			<div class="h-2.5 w-2.5 rounded-full" style="background-color: {laser.color};"></div>
			<span class="text-sm font-medium tabular-nums">
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
		<div class="text-fg-muted min-w-18 shrink-0 text-right font-mono text-sm text-nowrap tabular-nums">
			{#if typeof laser.powerMw === 'number'}
				{laser.powerMw.toFixed(1)} mW
			{/if}
		</div>

		<!-- Toggle -->
		<Switch class="shrink-0" checked={laser.isEnabled} onCheckedChange={() => laser.toggle()} />
	</button>
{/snippet}

{#snippet channelInfoPopover(cfg: ChannelConfig)}
	<Popover.Root>
		<Popover.Trigger
			class="text-fg-muted hover:text-fg hover:bg-element-hover flex items-center gap-1 rounded px-1 py-0.5 text-xs transition-colors"
		>
			<!-- <span>{cfg.label}</span> -->
			<InformationOutline width="11" height="11" />
		</Popover.Trigger>
		<Popover.Content
			class="bg-floating text-fg z-50 w-64 rounded border border-border p-3 text-left text-sm shadow-xl outline-none"
			sideOffset={4}
			side="top"
			align="end"
		>
			<div class="space-y-2">
				<div>
					{#if cfg.desc}
						<p class="text-fg mt-1 text-sm">{cfg.desc}</p>
					{/if}
				</div>
				<div class="text-fg space-y-1 border-t border-border pt-2 text-sm">
					{#if cfg.emission}
						<div class="flex justify-between gap-2">
							<span class="text-fg-muted">Emission</span>
							<span class="text-fg text-right">{cfg.emission} nm</span>
						</div>
					{/if}
					{#if cfg.detection}
						<div class="flex justify-between gap-2">
							<span class="text-fg-muted">Detection</span>
							<span class="text-fg text-right">{cfg.detection}</span>
						</div>
					{/if}
					{#if Object.keys(cfg.filters).length > 0}
						<div class="space-y-1">
							<div class="text-fg-muted mb-1 border-b border-border pt-1">Filters</div>
							{#each Object.entries(cfg.filters) as [wheelId, position] (position)}
								<div class="flex justify-between gap-2">
									<span class="text-fg-muted">{wheelId}:</span>
									<span class="text-fg text-right">{position}</span>
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
	<div class="bg-panel flex h-full w-96 flex-col justify-between gap-4">
		<div class="flex flex-col gap-4 px-3 py-4">
			<!-- Header -->
			<div class="flex items-center justify-between">
				<div class="flex items-center gap-2">
					<div class="h-3 w-3 rounded-full" style="background-color: {laser.color};"></div>
					<span class="text-base font-medium">
						{laser.wavelength ? `${laser.wavelength} nm` : 'Laser'}
					</span>
				</div>
				<div class="flex items-center gap-2">
					<span class="text-fg-muted text-xs">{laser.deviceId}</span>
					{#if cfg}
						{@render channelInfoPopover(cfg)}
					{/if}
				</div>
			</div>

			<!-- Power setpoint + quick actions -->
			{#if typeof laser.powerSetpoint === 'number'}
				<div class="space-y-3">
					<div>
						<h5 class="text-fg-muted mb-1.5 text-xs font-medium uppercase">Power Setpoint</h5>
						<SpinBox
							value={laser.powerSetpoint}
							min={0}
							max={laser.maxPower}
							step={1}
							decimals={1}
							suffix="mW"
							size="xs"
							class="w-full"
							onChange={(v) => laser.setPower(v)}
						/>
					</div>
					<div class="flex gap-1.5">
						{#each [0, 25, 50, 75, 100] as pct (pct)}
							{@const targetValue = (laser.maxPower * pct) / 100}
							<button
								onclick={() => laser.setPower(targetValue)}
								class="text-fg-muted hover:text-fg hover:bg-element-hover flex-1 rounded border border-border px-1 py-1 text-xs transition-colors"
							>
								{pct}%
							</button>
						{/each}
					</div>
				</div>
			{/if}

			<div class="space-y-3">
				<!-- Power readout -->
				<div class="flex items-baseline justify-between">
					<h5 class="text-fg-muted text-xs font-medium uppercase">Power</h5>
					<span class="text-fg font-mono text-sm tabular-nums">
						{typeof laser.powerMw === 'number' ? `${laser.powerMw.toFixed(1)} mW` : '—'}
					</span>
				</div>

				<!-- Temperature -->
				{#if typeof laser.temperatureC === 'number'}
					<div class="flex items-baseline justify-between">
						<h5 class="text-fg-muted text-xs font-medium uppercase">Temperature</h5>
						<span class="text-fg font-mono text-sm tabular-nums">{laser.temperatureC.toFixed(1)}°C</span>
					</div>
				{/if}
			</div>
		</div>

		<!-- Power history sparkline (all lasers) — fills remaining space -->
		<div class="flex max-h-36 min-h-12 flex-1 flex-col rounded-t-lg border-t border-border p-2">
			<p class="text-fg-muted pb-2font-mono pointer-events-none text-xs tabular-nums">
				All Lasers: {currentMaxPower.toFixed(0)} / {globalMaxPower.toFixed(0)} mW
			</p>
			{#if anyHistory}
				<svg viewBox="0 0 {POWER_HISTORY_MAX} 100" preserveAspectRatio="none" class="bg-canvas h-full w-full">
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
					<span class="text-fg-muted/50 text-xs">Collecting data...</span>
				</div>
			{/if}
		</div>
	</div>
{/snippet}

{#if allLasers.length === 0}
	<div class="flex h-full items-center justify-center">
		<p class="text-fg-muted text-sm">No lasers configured</p>
	</div>
{:else if selectedLaser}
	<div class="flex h-full">
		<!-- Right: laser list -->
		<div class="flex flex-1 flex-col overflow-auto border-r border-border px-4">
			<div class="flex h-full flex-col gap-3">
				{#if profileLasers.length > 0}
					<div>
						<div class="flex items-center justify-between py-3">
							<h4 class="text-fg-muted/60 text-xs font-medium uppercase">
								Active Profile <span class="text-fg-muted pl-2">{activeProfileLabel}</span>
							</h4>
							<button
								onclick={stopAllLasers}
								class="flex items-center gap-1.5 rounded bg-danger/20 px-2 py-1 text-sm text-danger transition-all hover:bg-danger/30 {anyLaserEnabled
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
						<h4 class="text-fg-muted/60 mb-1 text-xs font-medium uppercase">Other Lasers</h4>
						<div class="space-y-2">
							{#each otherLasers as laser (laser.deviceId)}
								{@render laserRow(laser)}
							{/each}
						</div>
					</div>
				{/if}
			</div>
		</div>

		<!-- Left: detail panel -->
		{@render detailPanel(
			selectedLaser,
			session.activeProfileId
				? (getChannelFor(session.config, session.activeProfileId, selectedLaser.deviceId)?.config ?? null)
				: null
		)}
	</div>
{/if}
