<script lang="ts">
	import type { Session, Camera } from '$lib/main';
	import type { ChannelConfig } from '$lib/main/types';
	import SpinBox from '$lib/ui/primitives/SpinBox.svelte';
	import Select from '$lib/ui/primitives/Select.svelte';
	import { Button, Checkbox } from '$lib/ui/primitives';
	import Icon from '@iconify/svelte';
	import { SvelteSet } from 'svelte/reactivity';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	const allCameras = $derived(Object.values(session.cameras));
	const allCameraIds = $derived(Object.keys(session.cameras));

	// Selection — default all selected
	let selectedIds = $state(new SvelteSet<string>());

	$effect(() => {
		if (selectedIds.size === 0 && allCameraIds.length > 0) {
			for (const id of allCameraIds) selectedIds.add(id);
		}
	});

	function toggleCamera(deviceId: string) {
		if (selectedIds.has(deviceId)) selectedIds.delete(deviceId);
		else selectedIds.add(deviceId);
	}

	function toggleAll() {
		if (selectedIds.size === allCameraIds.length) {
			selectedIds.clear();
		} else {
			for (const id of allCameraIds) selectedIds.add(id);
		}
	}

	const allSelected = $derived(allCameraIds.length > 0 && selectedIds.size === allCameraIds.length);
	const someSelected = $derived(selectedIds.size > 0 && selectedIds.size < allCameraIds.length);
	const selectedCameras = $derived(allCameras.filter((c) => selectedIds.has(c.deviceId)));

	// Channel map: camera deviceId -> { id, config }
	const cameraChannelMap = $derived.by(() => {
		const profile = session.activeProfile;
		const profileChannels: Record<string, ChannelConfig> = profile?.channels ?? {};
		const map = new Map<string, { id: string; config: ChannelConfig }>();
		for (const [channelId, config] of Object.entries(profileChannels)) {
			if (config.detection && !map.has(config.detection)) {
				map.set(config.detection, { id: channelId, config });
			}
		}
		return map;
	});

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
		return 'bg-muted-foreground/40';
	}

	function modeLabel(mode: string | undefined): string {
		if (mode === 'PREVIEW') return 'Preview';
		if (mode === 'ACQUISITION') return 'Acquiring';
		return 'Idle';
	}

	// Shared channel details state — expanding one expands all
	let channelExpanded = $state(false);
</script>

{#snippet cameraCard(camera: Camera)}
	{@const ch = cameraChannelMap.get(camera.deviceId)}
	{@const isSelected = selectedIds.has(camera.deviceId)}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<div
		role="button"
		tabindex="0"
		onclick={() => toggleCamera(camera.deviceId)}
		class="flex w-full cursor-pointer flex-col gap-3 rounded-md bg-muted/50 px-4 py-3 text-left"
	>
		<!-- Header: checkbox + device ID + mode -->
		<div class="flex items-center justify-between">
			<div class="flex items-center gap-2.5">
				<Checkbox checked={isSelected} size="sm" />
				<span class="text-sm font-medium">{camera.deviceId}</span>
			</div>
			<div class="flex items-center gap-1.5">
				<span class="text-[0.65rem] text-muted-foreground">{modeLabel(camera.mode)}</span>
				<div class="h-2 w-2 rounded-full {modeDotColor(camera.mode)}"></div>
			</div>
		</div>

		<!-- Properties -->
		<div class="space-y-1 text-xs">
			<div class="flex justify-between">
				<span class="text-muted-foreground">Exposure</span>
				<span class="font-mono tabular-nums">
					{camera.exposureTimeMs !== undefined ? `${camera.exposureTimeMs.toFixed(1)} ms` : '—'}
				</span>
			</div>
			<div class="flex justify-between">
				<span class="text-muted-foreground">Binning</span>
				<span class="font-mono tabular-nums">
					{camera.binning !== undefined ? `${camera.binning}x` : '—'}
				</span>
			</div>
			<div class="flex justify-between">
				<span class="text-muted-foreground">Format</span>
				<span class="font-mono tabular-nums">{camera.pixelFormat ?? '—'}</span>
			</div>
			<div class="flex justify-between">
				<span class="text-muted-foreground">Frame</span>
				<span class="font-mono tabular-nums">
					{#if camera.frameSizePx}
						{camera.frameSizePx.x}&times;{camera.frameSizePx.y}
					{:else}
						—
					{/if}
				</span>
			</div>
			<div class="flex justify-between">
				<span class="text-muted-foreground">Sensor</span>
				<span class="font-mono tabular-nums">
					{#if camera.sensorSizePx}
						{camera.sensorSizePx.x}&times;{camera.sensorSizePx.y}
					{:else}
						—
					{/if}
				</span>
			</div>
			<div class="flex justify-between">
				<span class="text-muted-foreground">Pixel</span>
				<span class="font-mono tabular-nums">
					{#if camera.pixelSizeUm}
						{camera.pixelSizeUm.x.toFixed(2)} &mu;m
					{:else}
						—
					{/if}
				</span>
			</div>
		</div>

		<!-- Channel -->
		{#if ch}
			<div class="border-t border-border/50 pt-2">
				<button
					onclick={(e) => { e.stopPropagation(); channelExpanded = !channelExpanded; }}
					class="flex w-full cursor-pointer items-center justify-between text-xs"
				>
					<span class="text-muted-foreground">Channel</span>
					<div class="flex items-center gap-1.5">
						<span class="font-mono tabular-nums">{ch.config.label ?? ch.id}</span>
						<Icon
							icon="mdi:chevron-right"
							width="14"
							height="14"
							class="text-muted-foreground transition-transform {channelExpanded ? 'rotate-90' : ''}"
						/>
					</div>
				</button>
				{#if channelExpanded}
					<div class="mt-2 space-y-1 text-xs">
						{#if ch.config.desc}
							<p class="text-muted-foreground">{ch.config.desc}</p>
						{/if}
						{#if ch.config.emission}
							<div class="flex justify-between">
								<span class="text-muted-foreground">Emission</span>
								<span class="font-mono tabular-nums">{ch.config.emission} nm</span>
							</div>
						{/if}
						{#if ch.config.illumination}
							<div class="flex justify-between">
								<span class="text-muted-foreground">Illumination</span>
								<span class="font-mono tabular-nums">{ch.config.illumination}</span>
							</div>
						{/if}
						{#if Object.keys(ch.config.filters).length > 0}
							{#each Object.entries(ch.config.filters) as [wheelId, position] (position)}
								<div class="flex justify-between">
									<span class="text-muted-foreground">{wheelId}</span>
									<span class="font-mono tabular-nums">{position}</span>
								</div>
							{/each}
						{/if}
					</div>
				{/if}
			</div>
		{/if}

		<!-- Stream info (when streaming) -->
		{#if camera.streamInfo}
			{@const info = camera.streamInfo}
			<div class="flex items-center gap-4 border-t border-border/50 pt-2 text-xs text-muted-foreground">
				<span class="font-mono tabular-nums">{info.frame_rate_fps.toFixed(1)} fps</span>
				<span class="font-mono tabular-nums">{info.data_rate_mbs.toFixed(1)} MB/s</span>
				{#if info.dropped_frames > 0}
					<span class="font-mono tabular-nums text-danger">{info.dropped_frames} dropped</span>
				{/if}
			</div>
		{/if}
	</div>
{/snippet}

{#snippet editPanel(cameras: Camera[])}
	<div class="flex h-full w-96 shrink-0 flex-col border-r border-border bg-card">
		<div class="flex-1 space-y-4 overflow-auto px-4 pt-4">
			<!-- Exposure -->
			<div>
				<h5 class="mb-1.5 text-[0.6rem] font-medium text-muted-foreground uppercase">Exposure</h5>
				<SpinBox
					value={formExposure ?? cameras[0]?.exposureTimeMs ?? 0}
					min={cameras[0]?.exposureMin ?? 0}
					max={cameras[0]?.exposureMax ?? 1000}
					step={cameras[0]?.exposureStep ?? 0.1}
					decimals={1}
					suffix="ms"
					size="sm"
						class="w-full"
					onChange={(v) => (formExposure = v)}
				/>
			</div>

			<!-- Binning -->
			{#if mergedBinningOptions.length > 0}
				<div>
					<h5 class="mb-1.5 text-[0.6rem] font-medium text-muted-foreground uppercase">Binning</h5>
					<Select
						value={formBinning ?? String(cameras[0]?.binning ?? '')}
						options={mergedBinningOptions.map((b) => ({ value: String(b), label: `${b}x` }))}
						size="sm"
						onchange={(v) => (formBinning = v)}
					/>
				</div>
			{/if}

			<!-- Pixel Format -->
			{#if mergedPixelFormatOptions.length > 0}
				<div>
					<h5 class="mb-1.5 text-[0.6rem] font-medium text-muted-foreground uppercase">Pixel Format</h5>
					<Select
						value={formPixelFormat ?? cameras[0]?.pixelFormat ?? ''}
						options={mergedPixelFormatOptions.map((f) => ({ value: f, label: f }))}
						size="sm"
						onchange={(v) => (formPixelFormat = v)}
					/>
				</div>
			{/if}

			<!-- Frame Region -->
			{#if cameras[0]?.frameRegion}
				{@const refRegion = cameras[0].frameRegion}
				<div>
					<h5 class="mb-1.5 text-[0.6rem] font-medium text-muted-foreground uppercase">Frame Region</h5>
					<div class="grid grid-cols-2 gap-2">
						<div>
							<span class="text-[0.55rem] text-muted-foreground">X</span>
							<SpinBox
								value={formRegionX ?? refRegion.x.value}
								min={refRegion.x.min_val}
								max={refRegion.x.max_val}
								step={refRegion.x.step}
								size="sm"
												class="w-full"
								onChange={(v) => (formRegionX = v)}
							/>
						</div>
						<div>
							<span class="text-[0.55rem] text-muted-foreground">Y</span>
							<SpinBox
								value={formRegionY ?? refRegion.y.value}
								min={refRegion.y.min_val}
								max={refRegion.y.max_val}
								step={refRegion.y.step}
								size="sm"
												class="w-full"
								onChange={(v) => (formRegionY = v)}
							/>
						</div>
						<div>
							<span class="text-[0.55rem] text-muted-foreground">Width</span>
							<SpinBox
								value={formRegionWidth ?? refRegion.width.value}
								min={refRegion.width.min_val}
								max={refRegion.width.max_val}
								step={refRegion.width.step}
								size="sm"
												class="w-full"
								onChange={(v) => (formRegionWidth = v)}
							/>
						</div>
						<div>
							<span class="text-[0.55rem] text-muted-foreground">Height</span>
							<SpinBox
								value={formRegionHeight ?? refRegion.height.value}
								min={refRegion.height.min_val}
								max={refRegion.height.max_val}
								step={refRegion.height.step}
								size="sm"
												class="w-full"
								onChange={(v) => (formRegionHeight = v)}
							/>
						</div>
					</div>
				</div>
			{/if}
		</div>

		<!-- Apply button -->
		<div class="px-4 py-3">
			<Button
				variant="default"
				size="sm"
				class="w-full"
				disabled={!hasFormChanges}
				onclick={applyChanges}
			>
				Apply to {cameras.length} camera{cameras.length !== 1 ? 's' : ''}
			</Button>
		</div>
	</div>
{/snippet}

{#if allCameras.length === 0}
	<div class="flex h-full items-center justify-center">
		<p class="text-xs text-muted-foreground">No cameras configured</p>
	</div>
{:else}
	<div class="flex h-full">
		<!-- Left: edit panel -->
		{#if selectedCameras.length > 0}
			{@render editPanel(selectedCameras)}
		{:else}
			<div class="flex h-full w-96 shrink-0 flex-col items-center justify-center border-r border-border bg-card">
				<p class="text-xs text-muted-foreground">Select cameras to edit</p>
			</div>
		{/if}

		<!-- Right: camera cards -->
		<div class="flex flex-1 flex-col overflow-auto px-4">
			<div class="flex h-full flex-col gap-2">
				<div class="flex items-center gap-2.5 py-3 pl-4">
					<Checkbox
						checked={allSelected}
						indeterminate={someSelected}
						onchange={toggleAll}
						size="sm"
					/>
					<span class="text-xs text-muted-foreground">
						{selectedIds.size} of {allCameras.length} camera{allCameras.length !== 1 ? 's' : ''} selected
					</span>
				</div>
				<div class="grid grid-cols-[repeat(auto-fit,minmax(16rem,1fr))] gap-2">
					{#each allCameras as camera (camera.deviceId)}
						{@render cameraCard(camera)}
					{/each}
				</div>
			</div>
		</div>
	</div>
{/if}
