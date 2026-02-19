<script lang="ts">
	import { type DevicesManager, parseVec2D } from '$lib/main';
	import SliderInput from '$lib/ui/primitives/SliderInput.svelte';
	import SelectInput from '$lib/ui/primitives/SelectInput.svelte';
	import CardAccordion from '$lib/ui/primitives/CardAccordion.svelte';

	interface Props {
		deviceId: string;
		devicesManager: DevicesManager;
	}

	let { deviceId, devicesManager }: Props = $props();

	// Reactive device properties
	let cameraDevice = $derived(devicesManager.getDevice(deviceId));

	// Exposure time control
	let exposureTimeModel = $derived(devicesManager.getPropertyModel(deviceId, 'exposure_time_ms'));
	let exposureTimeInfo = $derived(devicesManager.getPropertyInfo(deviceId, 'exposure_time_ms'));

	// Frame rate display
	let frameRateHz = $derived(devicesManager.getPropertyValue(deviceId, 'frame_rate_hz'));

	// Pixel format selector
	let pixelFormatModel = $derived(devicesManager.getPropertyModel(deviceId, 'pixel_format'));
	let pixelFormatInfo = $derived(devicesManager.getPropertyInfo(deviceId, 'pixel_format'));

	// Binning selector
	let binningModel = $derived(devicesManager.getPropertyModel(deviceId, 'binning'));
	let binningInfo = $derived(devicesManager.getPropertyInfo(deviceId, 'binning'));

	// Stream info
	let streamInfo = $derived(devicesManager.getPropertyValue(deviceId, 'stream_info'));

	let streamInfoSummary = $derived(
		!(streamInfo && typeof streamInfo === 'object')
			? typeof frameRateHz === 'number'
				? frameRateHz.toFixed(2)
				: 'N/A'
			: 'frame_rate_fps' in streamInfo && typeof streamInfo.frame_rate_fps === 'number'
				? streamInfo.frame_rate_fps.toFixed(2)
				: 'N/A'
	);

	// Sensor information (parsed as Vec2D)
	let sensorSize = $derived(parseVec2D(devicesManager.getPropertyValue(deviceId, 'sensor_size_px')));
	let pixelSize = $derived(parseVec2D(devicesManager.getPropertyValue(deviceId, 'pixel_size_um')));
	let frameSize = $derived(parseVec2D(devicesManager.getPropertyValue(deviceId, 'frame_size_px')));
	let frameSizeMb = $derived(devicesManager.getPropertyValue(deviceId, 'frame_size_mb'));

	// ROI
	let roiModel = $derived(devicesManager.getPropertyModel(deviceId, 'roi'));
	let roiInfo = $derived(devicesManager.getPropertyInfo(deviceId, 'roi'));
</script>

{#if cameraDevice?.connected}
	<div class="rounded-lg border border-zinc-700 bg-zinc-800/80 shadow-sm">
		<!-- Camera Header -->
		<div class="flex items-center justify-between px-3 py-2">
			<div class="text-sm font-medium text-zinc-200">Camera</div>
		</div>

		<div class="mb-4 flex flex-col gap-3">
			<!-- Exposure Time Slider -->
			<div class="px-3">
				{#if exposureTimeInfo && exposureTimeModel && typeof exposureTimeModel.value === 'number'}
					<SliderInput
						label={exposureTimeInfo.label}
						bind:value={exposureTimeModel.value}
						min={exposureTimeModel.min_val ?? 0}
						max={exposureTimeModel.max_val ?? 100}
						step={exposureTimeModel.step ?? 0.1}
						onChange={(newValue) => {
							devicesManager.setProperty(deviceId, 'exposure_time_ms', newValue);
						}}
					/>
				{/if}
			</div>

			<!-- Pixel Format and Binning Selectors -->
			<div class="grid grid-cols-2 gap-4 px-3">
				<!-- Pixel Format Selector -->
				{#if pixelFormatInfo && pixelFormatModel && pixelFormatModel.options && (typeof pixelFormatModel.value === 'string' || typeof pixelFormatModel.value === 'number')}
					<SelectInput
						label={pixelFormatInfo.label}
						bind:value={pixelFormatModel.value}
						options={pixelFormatModel.options}
						id="pixel-format-{deviceId}"
						onChange={(newValue) => {
							devicesManager.setProperty(deviceId, 'pixel_format', newValue);
						}}
					/>
				{/if}

				<!-- Binning Selector -->
				{#if binningInfo && binningModel && binningModel.options && (typeof binningModel.value === 'string' || typeof binningModel.value === 'number')}
					<SelectInput
						label={binningInfo.label}
						bind:value={binningModel.value}
						options={binningModel.options}
						id="binning-{deviceId}"
						formatOption={(option) => `${option}x${option}`}
						onChange={(newValue) => {
							devicesManager.setProperty(deviceId, 'binning', newValue);
						}}
					/>
				{/if}
			</div>
		</div>

		<!-- Sensor & ROI Collapsible Section (using CardAccordion component) -->
		{#if frameSize}
			{@const summary = `${frameSize.y} × ${frameSize.x} px${typeof frameSizeMb === 'number' ? ` | ${frameSizeMb.toFixed(2)} MB` : ''}`}
			<CardAccordion label="Frame Size" summaryValue={summary}>
				<!-- Sensor Size -->
				{#if sensorSize}
					<div class="flex justify-between">
						<span class="label">Sensor Size</span>
						<span class="value">{sensorSize.y} × {sensorSize.x} px</span>
					</div>
				{/if}

				<!-- Pixel Size -->
				{#if pixelSize}
					<div class="flex justify-between">
						<span class="label">Pixel Size</span>
						<span class="value">{pixelSize.y} × {pixelSize.x} µm</span>
					</div>
				{/if}

				<!-- ROI -->
				{#if roiInfo && roiModel && Array.isArray(roiModel.value) && roiModel.value.length === 4}
					<div class="flex justify-between">
						<span class="label">ROI</span>
						<span class="value">{roiModel.value[0]}, {roiModel.value[1]}, {roiModel.value[2]}, {roiModel.value[3]}</span
						>
					</div>
				{/if}
			</CardAccordion>
		{/if}

		<!-- Stream Info Collapsible Section -->
		<CardAccordion label="Stream Info" summaryValue={streamInfoSummary + ' fps'}>
			{#if streamInfo && typeof streamInfo === 'object'}
				{#if 'data_rate_mbs' in streamInfo && typeof streamInfo.data_rate_mbs === 'number'}
					<div class="flex justify-between">
						<span class="label">Data Rate</span>
						<span class="value">{streamInfo.data_rate_mbs.toFixed(1)} MB/s</span>
					</div>
				{/if}
				{#if 'dropped_frames' in streamInfo && typeof streamInfo.dropped_frames === 'number'}
					<div class="flex justify-between">
						<span class="label">Dropped Frames</span>
						<span class="value" class:text-red-400={streamInfo.dropped_frames > 0}>
							{streamInfo.dropped_frames}
						</span>
					</div>
				{/if}
				{#if 'frame_index' in streamInfo && typeof streamInfo.frame_index === 'number'}
					<div class="flex justify-between">
						<span class="label">Frame Index</span>
						<span class="value">{streamInfo.frame_index}</span>
					</div>
				{/if}
			{:else}
				<div class="value flex justify-center">
					<span class="text-zinc-600">Not Available</span>
				</div>
			{/if}
		</CardAccordion>
	</div>
{:else}
	<div class="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center text-xs text-zinc-500">
		Camera not available
	</div>
{/if}

<style>
	.label {
		font-size: 0.65rem;
		font-weight: 500;
		color: var(--color-zinc-400);
	}

	.value {
		font-size: 0.6rem;
		color: var(--color-zinc-300); /* text-zinc-300 */
	}
</style>
