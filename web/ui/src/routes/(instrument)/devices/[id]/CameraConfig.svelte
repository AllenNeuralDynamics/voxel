<script lang="ts">
	import type { Session } from '$lib/main';
	import { cn, sanitizeString } from '$lib/utils';
	import { SliderInput } from '$lib/ui/device';
	import { Select, SpinBox, Button } from '$lib/ui/kit';
	import DeviceBrowser from '$lib/ui/device/DeviceBrowser.svelte';

	const cameraExclusions = {
		props: [
			'exposure_time_ms',
			'pixel_format',
			'binning',
			'sensor_size_px',
			'pixel_size_um',
			'pixel_type',
			'frame_size_px',
			'frame_size_mb',
			'frame_area_mm',
			'frame_region',
			'frame_rate_hz',
			'stream_info'
		],
		cmds: ['update_frame_region']
	};

	interface Props {
		session: Session;
		deviceId: string;
	}

	let { session, deviceId }: Props = $props();

	let devicesManager = $derived(session.devices);
	let device = $derived(devicesManager.getDevice(deviceId));
	let camera = $derived(session.cameras[deviceId]);

	// Controls
	let exposureTimeModel = $derived(devicesManager.getPropertyModel(deviceId, 'exposure_time_ms'));
	let exposureTimeInfo = $derived(devicesManager.getPropertyInfo(deviceId, 'exposure_time_ms'));
	let pixelFormatModel = $derived(devicesManager.getPropertyModel(deviceId, 'pixel_format'));
	let pixelFormatInfo = $derived(devicesManager.getPropertyInfo(deviceId, 'pixel_format'));
	let binningModel = $derived(devicesManager.getPropertyModel(deviceId, 'binning'));
	let binningInfo = $derived(devicesManager.getPropertyInfo(deviceId, 'binning'));

	// Sensor details (right column)
	let sensorSize = $derived(camera?.sensorSizePx);
	let pixelSize = $derived(camera?.pixelSizeUm);
	let pixelType = $derived(devicesManager.getPropertyValue(deviceId, 'pixel_type'));
	let frameAreaMm = $derived(camera?.frameAreaMm);

	// Frame region (for SVG diagram)
	let frameRegion = $derived(camera?.frameRegion);
	let frameSize = $derived(camera?.frameSizePx);
	let frameSizeMb = $derived(camera?.frameSizeMb);

	// Stream info (hand-crafted in Stream column)
	let frameRateHz = $derived(devicesManager.getPropertyValue(deviceId, 'frame_rate_hz'));
	let streamInfo = $derived(camera?.streamInfo);

	// SVG dimensions — sensor defines the coordinate space
	let sensorW = $derived(sensorSize?.x ?? 1);
	let sensorH = $derived(sensorSize?.y ?? 1);

	// Local spinbox values — synced from frameRegion, sent on change
	let roiX = $state(0);
	let roiY = $state(0);
	let roiW = $state(0);
	let roiH = $state(0);

	// Sync local state when frameRegion updates from backend
	$effect(() => {
		if (frameRegion) {
			roiX = frameRegion.x.value;
			roiY = frameRegion.y.value;
			roiW = frameRegion.width.value;
			roiH = frameRegion.height.value;
		}
	});

	function updateRegion(patch: { x?: number; y?: number; width?: number; height?: number }) {
		camera?.updateFrameRegion(patch);
	}

	function resetRegion() {
		camera?.updateFrameRegion({ x: 0, y: 0, width: sensorW, height: sensorH });
	}

	// SVG stroke width scales with sensor size so it's visible but not fat
	let strokeWidth = $derived(Math.max(sensorW, sensorH) * 0.004);
</script>

<section class="space-y-5">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<h2 class="text-base font-medium text-fg">{sanitizeString(deviceId)}</h2>
		<span
			class={cn('h-2 w-2 rounded-full', device?.connected ? 'bg-success' : 'bg-fg-muted/30')}
			title={device?.connected ? 'Connected' : 'Disconnected'}
		></span>
	</div>

	{#if device?.connected}
		<div class="grid gap-6 lg:grid-cols-[3fr_2fr]">
			<!-- LEFT COLUMN: controls, frame region, dynamic rw, commands -->
			<div class="space-y-5">
				<!-- Exposure Time -->
				{#if exposureTimeInfo && exposureTimeModel && typeof exposureTimeModel.value === 'number'}
					<SliderInput
						label={exposureTimeInfo.label}
						bind:target={exposureTimeModel.value}
						min={exposureTimeModel.min_val ?? 0}
						max={exposureTimeModel.max_val ?? 100}
						step={exposureTimeModel.step ?? 0.1}
						onChange={(v) => devicesManager.setProperty(deviceId, 'exposure_time_ms', v)}
					/>
				{/if}

				<!-- Pixel Format and Binning -->
				<div class="grid grid-cols-2 gap-4">
					{#if pixelFormatInfo && pixelFormatModel && pixelFormatModel.options && (typeof pixelFormatModel.value === 'string' || typeof pixelFormatModel.value === 'number')}
						<div class="grid gap-1">
							<span class="text-xs font-medium text-fg-muted">{pixelFormatInfo.label}</span>
							<Select
								value={String(pixelFormatModel.value)}
								options={pixelFormatModel.options.map((o) => ({ value: String(o), label: String(o) }))}
								onchange={(v) => devicesManager.setProperty(deviceId, 'pixel_format', v)}
								size="xs"
							/>
						</div>
					{/if}

					{#if binningInfo && binningModel && binningModel.options && (typeof binningModel.value === 'string' || typeof binningModel.value === 'number')}
						<div class="grid gap-1">
							<span class="text-xs font-medium text-fg-muted">{binningInfo.label}</span>
							<Select
								value={String(binningModel.value)}
								options={binningModel.options.map((o) => ({ value: String(o), label: `${o}x${o}` }))}
								onchange={(v) => devicesManager.setProperty(deviceId, 'binning', Number(v))}
								size="xs"
							/>
						</div>
					{/if}
				</div>

				<!-- Frame Region -->
				<div class="space-y-3">
					<div class="flex items-baseline justify-between">
						<h4 class="text-xs font-medium tracking-wide text-fg-muted uppercase">Frame Region</h4>
						{#if frameSize}
							<span class="font-mono text-sm text-fg-muted">
								{frameSize.x} &times; {frameSize.y} px{#if frameSizeMb != null}
									&ensp;|&ensp;{frameSizeMb.toFixed(1)} MB{/if}
							</span>
						{/if}
					</div>

					<!-- SVG sensor diagram -->
					{#if sensorSize && frameRegion}
						<svg
							viewBox="0 0 {sensorW} {sensorH}"
							class="w-full rounded border border-border bg-element-bg"
							style="max-height: 280px;"
							preserveAspectRatio="xMidYMid meet"
						>
							<!-- Sensor area (full) -->
							<rect
								x={strokeWidth / 2}
								y={strokeWidth / 2}
								width={sensorW - strokeWidth}
								height={sensorH - strokeWidth}
								class="fill-none stroke-border"
								stroke-width={strokeWidth}
							/>

							<!-- Inactive sensor area overlay -->
							<rect x="0" y="0" width={sensorW} height={sensorH} class="fill-element-bg" />

							<!-- Active frame region -->
							<rect
								x={frameRegion.x.value}
								y={frameRegion.y.value}
								width={frameRegion.width.value}
								height={frameRegion.height.value}
								class="fill-primary/15 stroke-primary"
								stroke-width={strokeWidth}
							/>
						</svg>
					{:else}
						<div class="flex aspect-4/3 items-center justify-center rounded border border-border bg-element-bg">
							<span class="text-sm text-fg-muted">No region data</span>
						</div>
					{/if}

					<!-- ROI spinbox inputs -->
					{#if frameRegion}
						<div class="grid grid-cols-4 gap-2">
							<SpinBox
								value={roiX}
								prefix="x"
								min={frameRegion.x.min_val}
								max={frameRegion.x.max_val}
								step={frameRegion.x.step}
								onChange={(v) => updateRegion({ x: v })}
								appearance="bordered"
								size="xs"
							/>
							<SpinBox
								value={roiY}
								prefix="y"
								min={frameRegion.y.min_val}
								max={frameRegion.y.max_val}
								step={frameRegion.y.step}
								onChange={(v) => updateRegion({ y: v })}
								appearance="bordered"
								size="xs"
							/>
							<SpinBox
								value={roiW}
								prefix="w"
								min={frameRegion.width.min_val}
								max={frameRegion.width.max_val}
								step={frameRegion.width.step}
								onChange={(v) => updateRegion({ width: v })}
								appearance="bordered"
								size="xs"
							/>
							<SpinBox
								value={roiH}
								prefix="h"
								min={frameRegion.height.min_val}
								max={frameRegion.height.max_val}
								step={frameRegion.height.step}
								onChange={(v) => updateRegion({ height: v })}
								appearance="bordered"
								size="xs"
							/>
						</div>
						<Button variant="outline" size="sm" onclick={resetRegion} class="w-full">Reset Region</Button>
					{/if}
				</div>

				<!-- Dynamic: remaining properties + commands -->
				<DeviceBrowser {deviceId} {devicesManager} exclusions={cameraExclusions} />
			</div>

			<!-- RIGHT COLUMN: sensor info, stream -->
			<div class="space-y-5">
				<!-- Sensor / Pixel size -->
				<div class="grid gap-1 text-sm">
					{#if sensorSize}
						<div class="flex justify-between">
							<span class="text-fg-muted">Sensor</span>
							<span class="font-mono text-fg">{sensorSize.x} &times; {sensorSize.y} px</span>
						</div>
					{/if}
					{#if pixelSize}
						<div class="flex justify-between">
							<span class="text-fg-muted">Pixel</span>
							<span class="font-mono text-fg">{pixelSize.x} &times; {pixelSize.y} &micro;m</span>
						</div>
					{/if}
					{#if pixelType}
						<div class="flex justify-between">
							<span class="text-fg-muted">Type</span>
							<span class="font-mono text-fg">{pixelType}</span>
						</div>
					{/if}
					{#if frameAreaMm}
						<div class="flex justify-between">
							<span class="text-fg-muted">Area</span>
							<span class="font-mono text-fg">{frameAreaMm.x.toFixed(1)} &times; {frameAreaMm.y.toFixed(1)} mm</span>
						</div>
					{/if}
				</div>

				<!-- Stream info -->
				<div class="space-y-1">
					<h4 class="text-xs font-medium tracking-wide text-fg-muted uppercase">Stream</h4>
					<div class="grid gap-1 text-sm">
						<div class="flex justify-between">
							<span class="text-fg-muted">Frame Rate</span>
							<span class="font-mono text-fg">
								{typeof frameRateHz === 'number' ? `${frameRateHz.toFixed(1)} fps` : '\u2014'}
							</span>
						</div>
						<div class="flex justify-between">
							<span class="text-fg-muted">Data Rate</span>
							<span class="font-mono text-fg">
								{streamInfo?.data_rate_mbs != null ? `${streamInfo.data_rate_mbs.toFixed(1)} MB/s` : '\u2014'}
							</span>
						</div>
						<div class="flex justify-between">
							<span class="text-fg-muted">Dropped</span>
							<span class={cn('font-mono', streamInfo?.dropped_frames ? 'text-danger' : 'text-fg')}>
								{streamInfo?.dropped_frames != null ? streamInfo.dropped_frames : '\u2014'}
							</span>
						</div>
						<div class="flex justify-between">
							<span class="text-fg-muted">Frame Index</span>
							<span class="font-mono text-fg">
								{streamInfo?.frame_index != null ? streamInfo.frame_index : '\u2014'}
							</span>
						</div>
					</div>
				</div>
			</div>
		</div>
	{:else}
		<div class="flex items-center justify-center py-12">
			<p class="text-base text-fg-muted">Camera not available</p>
		</div>
	{/if}
</section>
