<script lang="ts">
	import {
		POWER_HISTORY_MAX,
		getChannelFor,
		isPropDiverged,
		formatPropValue,
		type Session,
		type Laser
	} from '$lib/main';
	import type { ChannelConfig } from '$lib/main/types';
	import Switch from '$lib/ui/kit/Switch.svelte';
	import SpinBox from '$lib/ui/kit/SpinBox.svelte';
	import Slider from '$lib/ui/kit/Slider.svelte';
	import { Button } from '$lib/ui/kit';
	import { Power, Restore } from '$lib/icons';
	import { Tooltip } from 'bits-ui';
	import { useInterval } from 'runed';
	import { cn } from '$lib/utils';

	interface Props {
		session: Session;
		profileId?: string;
		class?: string;
	}

	let { session, profileId, class: className }: Props = $props();

	const effectiveProfileId = $derived(profileId ?? session.activeProfileId);
	const profile = $derived(effectiveProfileId ? session.config.profiles[effectiveProfileId] : undefined);
	const isActiveProfile = $derived(!!effectiveProfileId && effectiveProfileId === session.activeProfileId);

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
		effectiveProfileId ? allLasers.filter((l) => getChannelFor(session.config, effectiveProfileId, l.deviceId)) : []
	);
	const otherLasers = $derived(
		effectiveProfileId
			? allLasers.filter((l) => !getChannelFor(session.config, effectiveProfileId, l.deviceId))
			: allLasers
	);

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

{#snippet laserRow(laser: Laser, cfg: ChannelConfig | null = null)}
	{@const savedProps = cfg ? profile?.props?.[laser.deviceId] : undefined}
	{@const savedPower = savedProps?.['power_setpoint_mw']}
	{@const powerDiverged = isPropDiverged(savedPower, laser.powerSetpoint)}
	{@const hasUnsaved = cfg && (savedPower === undefined || savedPower === null)}
	<button
		onclick={() => selectRow(laser.deviceId)}
		class="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors
			{selectedDeviceId === laser.deviceId ? 'bg-element-selected' : 'bg-surface hover:bg-element-hover'}"
	>
		<!-- Wavelength dot + label + divergence dot -->
		<div class="flex w-26 shrink-0 items-center gap-1">
			<div class="mr-1">
				{@render channelDot(laser, cfg)}
			</div>
			<span class="text-sm font-medium tabular-nums">
				{laser.wavelength ? `${laser.wavelength} nm` : 'Laser'}
			</span>
			{#if hasUnsaved}
				<span class="inline-block size-1 rounded-full bg-warning opacity-70"></span>
			{:else if powerDiverged}
				<span class="inline-block size-1 rounded-full bg-warning"></span>
			{/if}
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
		<div class="min-w-18 shrink-0 text-right font-mono text-sm text-nowrap text-fg-muted tabular-nums">
			{#if typeof laser.powerMw === 'number'}
				{laser.powerMw.toFixed(1)} mW
			{/if}
		</div>

		<!-- Toggle -->
		<Switch class="shrink-0" checked={laser.isEnabled} onCheckedChange={() => laser.toggle()} />
	</button>
{/snippet}

{#snippet channelDot(laser: Laser, cfg: ChannelConfig | null)}
	{#if cfg}
		<Tooltip.Provider>
			<Tooltip.Root delayDuration={200}>
				<Tooltip.Trigger
					class="flex h-3.5 w-3.5 cursor-pointer items-center justify-center rounded-full transition-shadow hover:ring-2 hover:ring-fg/20"
				>
					<div class="h-2.5 w-2.5 rounded-full" style="background-color: {laser.color};"></div>
				</Tooltip.Trigger>
				<Tooltip.Content
					class="z-50 w-64 rounded border border-border bg-floating p-3 text-left text-sm text-fg shadow-xl outline-none"
					sideOffset={6}
					side="bottom"
					align="start"
				>
					<div class="space-y-2">
						{#if cfg.desc}
							<p class="text-sm text-fg">{cfg.desc}</p>
						{/if}
						<div class="space-y-1 border-t border-border pt-2 text-sm text-fg">
							{#if cfg.emission}
								<div class="flex justify-between gap-2">
									<span class="text-fg-muted">Emission</span>
									<span class="text-right text-fg">{cfg.emission} nm</span>
								</div>
							{/if}
							{#if cfg.detection}
								<div class="flex justify-between gap-2">
									<span class="text-fg-muted">Detection</span>
									<span class="text-right text-fg">{cfg.detection}</span>
								</div>
							{/if}
							{#if Object.keys(cfg.filters).length > 0}
								<div class="space-y-1">
									<div class="mb-1 border-b border-border pt-1 text-fg-muted">Filters</div>
									{#each Object.entries(cfg.filters) as [wheelId, position] (position)}
										<div class="flex justify-between gap-2">
											<span class="text-fg-muted">{wheelId}:</span>
											<span class="text-right text-fg">{position}</span>
										</div>
									{/each}
								</div>
							{/if}
						</div>
					</div>
				</Tooltip.Content>
			</Tooltip.Root>
		</Tooltip.Provider>
	{:else}
		<div class="h-2.5 w-2.5 rounded-full" style="background-color: {laser.color};"></div>
	{/if}
{/snippet}

{#snippet detailPanel(laser: Laser, cfg: ChannelConfig | null)}
	{@const savedProps = cfg ? profile?.props?.[laser.deviceId] : undefined}
	{@const savedPower = savedProps?.['power_setpoint_mw']}
	{@const powerDiverged = isPropDiverged(savedPower, laser.powerSetpoint)}
	{@const hasUnsaved = cfg && (savedPower === undefined || savedPower === null)}
	<div class="flex h-full w-72 flex-col justify-between gap-4 border-r border-border bg-panel @[800px]:w-96">
		<div class="flex flex-col gap-4 px-4 py-2">
			<!-- Header -->
			<div class="flex items-center justify-between">
				<div class="flex h-ui-sm items-center gap-2 text-xs text-fg-muted">
					{@render channelDot(laser, cfg)}
					<span class="text-base font-medium">
						{laser.wavelength ? `${laser.wavelength} nm` : 'Laser'}
					</span>
					<span>·</span>
					<span>{laser.deviceId}</span>
				</div>
				<div class="flex items-center gap-2">
					{#if isActiveProfile && cfg}
						{#if powerDiverged || hasUnsaved}
							<Button
								variant="ghost"
								size="icon-xs"
								onclick={() => session.applyProfileProps([laser.deviceId])}
								title="Revert to saved"
							>
								<Restore width="14" height="14" />
							</Button>
						{/if}
						<Button variant="outline" size="xs" onclick={() => session.saveProfileProps(laser.deviceId)}>Save</Button>
					{/if}
				</div>
			</div>

			<!-- Power setpoint + quick actions -->
			{#if typeof laser.powerSetpoint === 'number'}
				<div class="space-y-3">
					<div>
						<div class="mb-1.5 flex items-center gap-1.5">
							<h5 class="text-xs font-medium text-fg-muted uppercase">Power Setpoint</h5>
							{#if hasUnsaved}
								<span class="inline-block size-1 rounded-full bg-warning opacity-70"></span>
							{:else if powerDiverged}
								<span class="text-xs text-warning opacity-90">({formatPropValue(savedPower, 1)})</span>
							{/if}
						</div>
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
								class="flex-1 rounded border border-border px-1 py-1 text-xs text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
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
					<h5 class="text-xs font-medium text-fg-muted uppercase">Power</h5>
					<span class="font-mono text-sm text-fg tabular-nums">
						{typeof laser.powerMw === 'number' ? `${laser.powerMw.toFixed(1)} mW` : '—'}
					</span>
				</div>

				<!-- Temperature -->
				{#if typeof laser.temperatureC === 'number'}
					<div class="flex items-baseline justify-between">
						<h5 class="text-xs font-medium text-fg-muted uppercase">Temperature</h5>
						<span class="font-mono text-sm text-fg tabular-nums">{laser.temperatureC.toFixed(1)}°C</span>
					</div>
				{/if}
			</div>
		</div>

		<!-- Power history sparkline (all lasers) — fills remaining space -->
		<div class="flex max-h-48 min-h-24 flex-1 flex-col border-t border-border p-4 pt-2 pb-6">
			<p class="pointer-events-none pb-2 font-mono text-xs text-fg-muted tabular-nums">
				Max Power: {currentMaxPower.toFixed(0)} / {globalMaxPower.toFixed(0)} mW
			</p>
			{#if anyHistory}
				<svg
					viewBox="0 0 {POWER_HISTORY_MAX} 100"
					preserveAspectRatio="none"
					class="h-full w-full rounded-md bg-canvas"
				>
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
					<span class="text-xs text-fg-muted/50">Collecting data...</span>
				</div>
			{/if}
		</div>
	</div>
{/snippet}

{#if allLasers.length === 0}
	<div class={cn('flex h-full items-center justify-center', className)}>
		<p class="text-sm text-fg-muted">No lasers configured</p>
	</div>
{:else if selectedLaser}
	{@const groupLabelClasses = 'text-xs leading-ui-sm font-medium text-fg-muted/60 uppercase'}
	<div class={cn('@container flex h-full flex-row-reverse', className)}>
		<!-- Right: laser list -->
		<div class="flex flex-1 flex-col overflow-auto px-4">
			<div class="flex h-full flex-col gap-3">
				{#if profileLasers.length > 0}
					<div>
						<div class="flex items-center justify-between py-2">
							<h4 class={groupLabelClasses}>This Profile</h4>
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
								{@render laserRow(
									laser,
									effectiveProfileId
										? (getChannelFor(session.config, effectiveProfileId, laser.deviceId)?.config ?? null)
										: null
								)}
							{/each}
						</div>
					</div>
				{/if}

				{#if otherLasers.length > 0}
					<div class="">
						<div class="flex items-center justify-between py-2">
							<h4 class={groupLabelClasses}>Other Lasers</h4>
						</div>
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
