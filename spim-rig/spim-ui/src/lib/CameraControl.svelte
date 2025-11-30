<script lang="ts">
	import type { DevicesManager } from '$lib/core';
	import SliderInput from '$lib/ui/SliderInput.svelte';
	import SelectInput from '$lib/ui/SelectInput.svelte';

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
</script>

{#if cameraDevice?.connected}
	<div class="space-y-2 rounded-lg border border-zinc-700 bg-zinc-800/80 shadow-sm">
		<!-- Camera Header -->
		<div class="flex items-center justify-between px-3 pt-3">
			<div class="text-sm font-medium text-zinc-200">Camera</div>
		</div>

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

		<!-- Footer: Frame Rate and Stream Info (single row, fixed height) -->
		<div
			class="mt-4 flex items-center justify-between border-t border-zinc-700 px-3 py-2 font-mono text-xs text-zinc-300"
		>
			<!-- Frame Rate (always shown) -->
			{#if typeof frameRateHz === 'number'}
				<div class="flex flex-1 items-center justify-between gap-1">
					<span class="text-zinc-500">Frame Rate:</span>
					<span>{frameRateHz.toFixed(1)} Hz</span>
				</div>
			{/if}

			<!-- Stream Info (only when streaming, on the right) -->
			{#if streamInfo && typeof streamInfo === 'object'}
				<div class="flex items-center gap-2">
					{#if 'frame_rate' in streamInfo && typeof streamInfo.frame_rate === 'number'}
						<div class="flex items-center gap-1">
							<span class="text-zinc-500">FPS:</span>
							<span>{streamInfo.frame_rate.toFixed(1)}</span>
						</div>
					{/if}
					{#if 'data_rate_mb_s' in streamInfo && typeof streamInfo.data_rate_mb_s === 'number'}
						<span class="text-zinc-600">|</span>
						<span>{streamInfo.data_rate_mb_s.toFixed(1)} MB/s</span>
					{/if}
					{#if 'dropped_frames' in streamInfo && typeof streamInfo.dropped_frames === 'number'}
						<span class="text-zinc-600">|</span>
						<span class={streamInfo.dropped_frames > 0 ? 'text-red-400' : ''}>
							{streamInfo.dropped_frames} dropped
						</span>
					{/if}
				</div>
			{/if}
		</div>
	</div>
{:else}
	<div class="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center text-xs text-zinc-500">
		Camera not available
	</div>
{/if}
