<script lang="ts">
	import { getChannelFor, isPropDiverged, formatPropValue, type Session, type Camera } from '$lib/main';
	import SpinBox from '$lib/ui/kit/SpinBox.svelte';
	import Select from '$lib/ui/kit/Select.svelte';
	import { Button, Checkbox } from '$lib/ui/kit';
	import { Restore } from '$lib/icons';
	import { SvelteSet } from 'svelte/reactivity';
	import { watch } from 'runed';
	import { slide } from 'svelte/transition';
	import { cn } from '$lib/utils';

	interface Props {
		session: Session;
		profileId?: string;
		panelSide?: 'left' | 'right';
		class?: string;
	}

	let { session, profileId, panelSide = 'left', class: className }: Props = $props();

	const panelRight = $derived(panelSide === 'right');

	// ── Profile context ──
	const effectiveProfileId = $derived(profileId ?? session.activeProfileId);
	const profile = $derived(effectiveProfileId ? session.config.profiles[effectiveProfileId] : undefined);
	const isActiveProfile = $derived(!!effectiveProfileId && effectiveProfileId === session.activeProfileId);

	// ── Profile cameras ──
	const allCameras = $derived(Object.values(session.cameras));
	const profileCameraIds = $derived.by(() => {
		if (!profile) return new Set<string>();
		return new Set(profile.channels.map((chId) => session.config.channels[chId]?.detection).filter(Boolean));
	});
	const cameras = $derived(allCameras.filter((c) => profileCameraIds.has(c.deviceId)));
	const otherCameras = $derived(allCameras.filter((c) => !profileCameraIds.has(c.deviceId)));

	// ── Selection (reset to all on profile switch) ──
	let selectedIds = new SvelteSet<string>();

	watch(
		() => effectiveProfileId,
		() => {
			selectedIds.clear();
			for (const c of cameras) selectedIds.add(c.deviceId);
		}
	);

	function toggleCamera(deviceId: string) {
		if (selectedIds.has(deviceId)) selectedIds.delete(deviceId);
		else selectedIds.add(deviceId);
	}

	function toggleAll() {
		if (selectedIds.size === cameras.length) selectedIds.clear();
		else for (const c of cameras) selectedIds.add(c.deviceId);
	}

	const allSelected = $derived(cameras.length > 0 && selectedIds.size === cameras.length);
	const someSelected = $derived(selectedIds.size > 0 && selectedIds.size < cameras.length);
	const selectedCameras = $derived(cameras.filter((c) => selectedIds.has(c.deviceId)));
	const selectedHasDivergence = $derived(
		selectedCameras.some((c) => session.devices.hasDivergence(c.deviceId, profile?.props?.[c.deviceId]))
	);

	// Form state — undefined means "no change"
	let formExposure = $state<number | undefined>(undefined);
	let formBinning = $state<string | undefined>(undefined);
	let formPixelFormat = $state<string | undefined>(undefined);
	let formRegionX = $state<number | undefined>(undefined);
	let formRegionY = $state<number | undefined>(undefined);
	let formRegionWidth = $state<number | undefined>(undefined);
	let formRegionHeight = $state<number | undefined>(undefined);

	const hasFormChanges = $derived(
		formExposure !== undefined ||
			formBinning !== undefined ||
			formPixelFormat !== undefined ||
			formRegionX !== undefined ||
			formRegionY !== undefined ||
			formRegionWidth !== undefined ||
			formRegionHeight !== undefined
	);

	function applyChanges() {
		for (const cam of selectedCameras) {
			if (formExposure !== undefined) cam.setExposure(formExposure);
			if (formBinning !== undefined) cam.setBinning(Number(formBinning));
			if (formPixelFormat !== undefined) cam.setPixelFormat(formPixelFormat);

			const regionUpdate: { x?: number; y?: number; width?: number; height?: number } = {};
			if (formRegionX !== undefined) regionUpdate.x = formRegionX;
			if (formRegionY !== undefined) regionUpdate.y = formRegionY;
			if (formRegionWidth !== undefined) regionUpdate.width = formRegionWidth;
			if (formRegionHeight !== undefined) regionUpdate.height = formRegionHeight;
			if (Object.keys(regionUpdate).length > 0) cam.updateFrameRegion(regionUpdate);
		}
		resetForm();
	}

	function resetForm() {
		formExposure = undefined;
		formBinning = undefined;
		formPixelFormat = undefined;
		formRegionX = undefined;
		formRegionY = undefined;
		formRegionWidth = undefined;
		formRegionHeight = undefined;
	}

	// Merged options from selected cameras
	const mergedBinningOptions = $derived.by(() => {
		const sets = selectedCameras.map((c) => new Set(c.binningOptions));
		if (sets.length === 0) return [];
		let common = sets[0];
		for (let i = 1; i < sets.length; i++) {
			common = new Set([...common].filter((v) => sets[i].has(v)));
		}
		return [...common].sort((a, b) => a - b);
	});

	const mergedPixelFormatOptions = $derived.by(() => {
		const sets = selectedCameras.map((c) => new Set(c.pixelFormatOptions));
		if (sets.length === 0) return [];
		let common = sets[0];
		for (let i = 1; i < sets.length; i++) {
			common = new Set([...common].filter((v) => sets[i].has(v)));
		}
		return [...common].sort();
	});

	function modeDotColor(mode: string | undefined): string {
		if (mode === 'PREVIEW') return 'bg-success';
		if (mode === 'ACQUISITION') return 'bg-warning';
		return 'bg-fg-muted/40';
	}

	function modeLabel(mode: string | undefined): string {
		if (mode === 'PREVIEW') return 'Preview';
		if (mode === 'ACQUISITION') return 'Acquiring';
		return 'Idle';
	}
</script>

{#snippet unsavedDot(saved: unknown)}
	{#if saved === undefined || saved === null}
		<span class="inline-block size-1 rounded-full bg-warning opacity-70"></span>
	{/if}
{/snippet}

{#snippet cameraCard(camera: Camera)}
	{@const ch = effectiveProfileId ? getChannelFor(session.config, effectiveProfileId, camera.deviceId) : undefined}
	{@const isSelected = selectedIds.has(camera.deviceId)}
	{@const savedProps = profile?.props?.[camera.deviceId]}
	{@const savedExp = savedProps?.['exposure_time_ms']}
	{@const savedBin = savedProps?.['binning']}
	{@const savedFmt = savedProps?.['pixel_format']}
	{@const expDiverged = isPropDiverged(savedExp, camera.exposureTimeMs)}
	{@const binDiverged = isPropDiverged(savedBin, camera.binning)}
	{@const fmtDiverged = isPropDiverged(savedFmt, camera.pixelFormat)}

	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class={cn(
			'flex w-full flex-col gap-3 rounded border px-3 py-2 text-left transition-colors',
			isActiveProfile && 'cursor-pointer',
			isSelected && isActiveProfile
				? 'border-fg-faint/60 bg-element-bg/70 hover:bg-element-bg'
				: 'border-border hover:bg-element-hover/50'
		)}
		onclick={() => isActiveProfile && toggleCamera(camera.deviceId)}
	>
		<!-- Header: name + channel badge + mode badge + checkbox -->
		<div class="flex items-center gap-2.5">
			<span class="text-base font-medium">{camera.deviceId}</span>
			{#if ch}
				<span class="rounded-full bg-element-bg px-1.5 py-px text-xs text-fg-muted">{ch.config.label ?? ch.id}</span>
			{/if}
			<div class="ml-auto flex items-center gap-2.5">
				<div class="flex items-center gap-1.5">
					<div class="h-2 w-2 rounded-full {modeDotColor(camera.mode)}"></div>
					<span class="text-xs text-fg-muted">{modeLabel(camera.mode)}</span>
				</div>
				{#if isActiveProfile}
					<Checkbox checked={isSelected} size="sm" class="pointer-events-none border-fg-faint" />
				{/if}
			</div>
		</div>

		<!-- Properties -->
		<div class="space-y-1 text-sm">
			<div class="flex justify-between">
				<div class="flex items-center gap-1">
					<span class="text-fg-muted">Exposure</span>
					{@render unsavedDot(savedExp)}
				</div>
				<div class="flex items-center gap-1 font-mono tabular-nums">
					{camera.exposureTimeMs !== undefined ? `${camera.exposureTimeMs.toFixed(1)} ms` : '—'}
					{#if expDiverged}
						<span class="text-warning opacity-90">({formatPropValue(savedExp, 0.1)})</span>
					{/if}
				</div>
			</div>
			<div class="flex justify-between">
				<div class="flex items-center gap-1">
					<span class="text-fg-muted">Binning</span>
					{@render unsavedDot(savedBin)}
				</div>
				<div class="flex items-center gap-1 font-mono tabular-nums">
					{camera.binning !== undefined ? `${camera.binning}x` : '—'}
					{#if binDiverged}
						<span class="text-warning opacity-90">({formatPropValue(savedBin)})</span>
					{/if}
				</div>
			</div>
			<div class="flex justify-between">
				<div class="flex items-center gap-1">
					<span class="text-fg-muted">Format</span>
					{@render unsavedDot(savedFmt)}
				</div>
				<div class="flex items-center gap-1 font-mono tabular-nums">
					{camera.pixelFormat ?? '—'}
					{#if fmtDiverged}
						<span class="text-warning opacity-90">({formatPropValue(savedFmt)})</span>
					{/if}
				</div>
			</div>
			<div class="flex justify-between">
				<span class="text-fg-muted">Frame</span>
				<span class="font-mono tabular-nums">
					{#if camera.frameSizePx}
						{camera.frameSizePx.x}&times;{camera.frameSizePx.y}
					{:else}
						—
					{/if}
				</span>
			</div>
			<div class="flex justify-between">
				<span class="text-fg-muted">Sensor</span>
				<span class="font-mono tabular-nums">
					{#if camera.sensorSizePx}
						{camera.sensorSizePx.x}&times;{camera.sensorSizePx.y}
					{:else}
						—
					{/if}
				</span>
			</div>
			<div class="flex justify-between">
				<span class="text-fg-muted">Pixel</span>
				<span class="font-mono tabular-nums">
					{#if camera.pixelSizeUm}
						{camera.pixelSizeUm.x.toFixed(2)} &mu;m
					{:else}
						—
					{/if}
				</span>
			</div>
		</div>
		<!-- Stream info (when streaming) -->
		{#if camera.streamInfo}
			{@const info = camera.streamInfo}
			<div class="flex items-center gap-4 border-t border-border/50 pt-2 text-sm text-fg-muted">
				<span class="font-mono tabular-nums">{info.frame_rate_fps.toFixed(1)} fps</span>
				<span class="font-mono tabular-nums">{info.data_rate_mbs.toFixed(1)} MB/s</span>
				{#if info.dropped_frames > 0}
					<span class="font-mono text-danger tabular-nums">{info.dropped_frames} dropped</span>
				{/if}
			</div>
		{/if}
	</div>
{/snippet}

{#snippet otherCameraCard(camera: Camera)}
	<div
		class="flex w-full cursor-not-allowed flex-col gap-3 rounded border border-border px-3 py-2 text-left opacity-80"
	>
		<!-- Header: name + mode badge -->
		<div class="flex items-center gap-2.5">
			<span class="text-base font-medium">{camera.deviceId}</span>
			<div class="ml-auto flex items-center gap-1.5">
				<div class="h-2 w-2 rounded-full {modeDotColor(camera.mode)}"></div>
				<span class="text-xs text-fg-muted">{modeLabel(camera.mode)}</span>
			</div>
		</div>

		<!-- Properties -->
		<div class="space-y-1 text-sm">
			<div class="flex justify-between">
				<span class="text-fg-muted">Exposure</span>
				<span class="font-mono tabular-nums">
					{camera.exposureTimeMs !== undefined ? `${camera.exposureTimeMs.toFixed(1)} ms` : '—'}
				</span>
			</div>
			<div class="flex justify-between">
				<span class="text-fg-muted">Binning</span>
				<span class="font-mono tabular-nums">{camera.binning !== undefined ? `${camera.binning}x` : '—'}</span>
			</div>
			<div class="flex justify-between">
				<span class="text-fg-muted">Frame</span>
				<span class="font-mono tabular-nums">
					{#if camera.frameSizePx}
						{camera.frameSizePx.x}&times;{camera.frameSizePx.y}
					{:else}
						—
					{/if}
				</span>
			</div>
		</div>
	</div>
{/snippet}

{#if !profile}
	<div class={cn('flex items-center justify-center py-12', className)}>
		<p class="text-sm text-fg-muted">No active profile</p>
	</div>
{:else if cameras.length === 0 && otherCameras.length === 0}
	<div class={cn('flex items-center justify-center py-12', className)}>
		<p class="text-sm text-fg-muted">No cameras configured</p>
	</div>
{:else}
	<div class={cn('flex', className)}>
		<!-- Cards column (header + cards) -->
		<div class={cn('flex min-w-0 flex-1 flex-col gap-3 px-3 py-3', panelRight ? 'order-first' : 'order-last')}>
			<!-- Header bar (only when active profile) -->
			{#if isActiveProfile}
				<div class="-mt-1.5 flex h-ui-sm items-center justify-between">
					<div class="flex items-center gap-2.5">
						<Checkbox checked={allSelected} indeterminate={someSelected} onchange={toggleAll} size="sm" />
						<span class="text-sm text-fg-muted">
							{selectedIds.size} of {cameras.length} camera{cameras.length !== 1 ? 's' : ''} selected
						</span>
					</div>
					{#if selectedCameras.length > 0}
						<div class="flex items-center gap-1">
							{#if selectedHasDivergence}
								<Button
									variant="ghost"
									size="icon-xs"
									onclick={() => session.applyProfileProps([...selectedIds])}
									title="Revert selected to saved"
								>
									<Restore width="14" height="14" />
								</Button>
							{/if}
							<Button
								variant="outline"
								size="xs"
								onclick={() => {
									for (const id of selectedIds) session.saveProfileProps(id);
								}}
							>
								Save
							</Button>
						</div>
					{/if}
				</div>
			{/if}

			<div class="flex-1 overflow-auto">
				<div class="grid grid-cols-[repeat(auto-fit,minmax(20rem,1fr))] gap-x-4 gap-y-2">
					{#each cameras as camera (camera.deviceId)}
						{@render cameraCard(camera)}
					{/each}
					{#if otherCameras.length > 0}
						{#each otherCameras as camera (camera.deviceId)}
							{@render otherCameraCard(camera)}
						{/each}
					{/if}
				</div>
			</div>
		</div>

		<!-- Sidebar (visible when active profile) -->
		{#if isActiveProfile}
			<div
				class={cn(
					'flex min-h-96 w-96 shrink-0 flex-col bg-panel px-3',
					panelRight ? 'order-last border-l border-border' : 'order-first border-r border-border'
				)}
				transition:slide={{ axis: 'x', duration: 200 }}
			>
				{#if selectedCameras.length > 0}
					<div class="flex-1 space-y-4 overflow-auto pt-4">
						<!-- Exposure -->
						<div>
							<h5 class="mb-1.5 text-xs font-medium text-fg-muted uppercase">Exposure</h5>
							<SpinBox
								value={formExposure ?? selectedCameras[0]?.exposureTimeMs ?? 0}
								min={selectedCameras[0]?.exposureMin ?? 0}
								max={selectedCameras[0]?.exposureMax ?? 1000}
								step={selectedCameras[0]?.exposureStep ?? 0.1}
								decimals={1}
								suffix="ms"
								size="xs"
								class="w-full"
								onChange={(v) => (formExposure = v)}
							/>
						</div>

						<!-- Binning & Pixel Format -->
						{#if mergedBinningOptions.length > 0 || mergedPixelFormatOptions.length > 0}
							<div class="grid grid-cols-2 gap-2">
								{#if mergedBinningOptions.length > 0}
									<div>
										<h5 class="mb-1.5 text-xs font-medium text-fg-muted uppercase">Binning</h5>
										<Select
											value={formBinning ?? String(selectedCameras[0]?.binning ?? '')}
											options={mergedBinningOptions.map((b) => ({ value: String(b), label: `${b}x` }))}
											size="xs"
											onchange={(v) => (formBinning = v)}
										/>
									</div>
								{/if}
								{#if mergedPixelFormatOptions.length > 0}
									<div>
										<h5 class="mb-1.5 text-xs font-medium text-fg-muted uppercase">Pixel Format</h5>
										<Select
											value={formPixelFormat ?? selectedCameras[0]?.pixelFormat ?? ''}
											options={mergedPixelFormatOptions.map((f) => ({ value: f, label: f }))}
											size="xs"
											onchange={(v) => (formPixelFormat = v)}
										/>
									</div>
								{/if}
							</div>
						{/if}

						<!-- Frame Region -->
						{#if selectedCameras[0]?.frameRegion}
							{@const refRegion = selectedCameras[0].frameRegion}
							<div>
								<h5 class="mb-1.5 text-xs text-fg-faint capitalize">Frame Region</h5>
								<div class="grid grid-cols-2 gap-2">
									<div>
										<span class="text-xs text-fg-muted">X</span>
										<SpinBox
											value={formRegionX ?? refRegion.x.value}
											min={refRegion.x.min_val}
											max={refRegion.x.max_val}
											step={refRegion.x.step}
											size="xs"
											class="w-full"
											onChange={(v) => (formRegionX = v)}
										/>
									</div>
									<div>
										<span class="text-xs text-fg-muted">Y</span>
										<SpinBox
											value={formRegionY ?? refRegion.y.value}
											min={refRegion.y.min_val}
											max={refRegion.y.max_val}
											step={refRegion.y.step}
											size="xs"
											class="w-full"
											onChange={(v) => (formRegionY = v)}
										/>
									</div>
									<div>
										<span class="text-xs text-fg-muted uppercase">Width</span>
										<SpinBox
											value={formRegionWidth ?? refRegion.width.value}
											min={refRegion.width.min_val}
											max={refRegion.width.max_val}
											step={refRegion.width.step}
											size="xs"
											class="w-full"
											onChange={(v) => (formRegionWidth = v)}
										/>
									</div>
									<div>
										<span class="text-xs text-fg-muted uppercase">Height</span>
										<SpinBox
											value={formRegionHeight ?? refRegion.height.value}
											min={refRegion.height.min_val}
											max={refRegion.height.max_val}
											step={refRegion.height.step}
											size="xs"
											class="w-full"
											onChange={(v) => (formRegionHeight = v)}
										/>
									</div>
								</div>
							</div>
						{/if}
					</div>

					<!-- Apply button -->
					<Button variant="secondary" class="my-3 w-full" disabled={!hasFormChanges} onclick={applyChanges}>
						Apply to {selectedCameras.length} camera{selectedCameras.length !== 1 ? 's' : ''}
					</Button>
				{:else}
					<div class="flex flex-1 items-center justify-center">
						<p class="text-sm text-fg-muted">Select cameras to edit</p>
					</div>
				{/if}
			</div>
		{/if}
	</div>
{/if}
