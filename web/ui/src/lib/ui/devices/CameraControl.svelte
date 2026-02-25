<script lang="ts">
	import type { Snippet } from 'svelte';
	import { type DevicesManager, parseVec2D } from '$lib/main';
	import SliderInput from '$lib/ui/SliderInput.svelte';
	import Select from '$lib/ui/primitives/Select.svelte';
	import Icon from '@iconify/svelte';

	interface Props {
		deviceId: string;
		devicesManager: DevicesManager;
		collapsed?: boolean;
	}

	let { deviceId, devicesManager, collapsed = false }: Props = $props();

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

{#snippet collapsible(label: string, summaryValue: string, body: Snippet)}
	<details class="group border-t border-zinc-700">
		<summary
			class="flex cursor-pointer items-center justify-between px-3 py-2 font-mono text-xs transition-colors hover:bg-zinc-700/30"
		>
			<div class="flex items-center gap-1">
				<span class="text-[0.65rem] font-medium text-zinc-400">{label}</span>
				<Icon icon="mdi:chevron-right" class="text-zinc-500 transition-transform group-open:rotate-90" />
			</div>
			<span class="text-[0.6rem] text-zinc-300">{summaryValue}</span>
		</summary>
		<div class="space-y-2 bg-zinc-800/40 px-3 pb-2 text-xs">
			{@render body()}
		</div>
	</details>
{/snippet}

{#if cameraDevice?.connected}
	{#if collapsed}
		<div class="flex items-center justify-between py-1 font-mono text-[0.6rem] text-zinc-300">
			<span class="text-zinc-400/90">Camera</span>
			<div class="flex items-center">
				{#if typeof frameRateHz === 'number'}
					<span>{frameRateHz.toFixed(1)} Hz</span>
				{/if}
				{#if typeof exposureTimeModel?.value === 'number'}
					<div class="mx-3 h-2.5 w-px bg-zinc-500"></div>
					<span>{exposureTimeModel.value.toFixed(1)} ms</span>
				{/if}
					<div class="ml-3 h-1.5 w-1.5 rounded-full {streamInfo ? 'bg-emerald-500' : 'bg-zinc-600'}"></div>
			</div>
		</div>
	{:else}
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
							bind:target={exposureTimeModel.value}
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
						<div class="grid gap-1">
							<span class="text-left text-[0.65rem] font-medium text-zinc-400">{pixelFormatInfo.label}</span>
							<Select
								value={String(pixelFormatModel.value)}
								options={pixelFormatModel.options.map((o) => ({ value: String(o), label: String(o) }))}
								onchange={(v) => devicesManager.setProperty(deviceId, 'pixel_format', v)}
								size="sm"
							/>
						</div>
					{/if}

					<!-- Binning Selector -->
					{#if binningInfo && binningModel && binningModel.options && (typeof binningModel.value === 'string' || typeof binningModel.value === 'number')}
						<div class="grid gap-1">
							<span class="text-left text-[0.65rem] font-medium text-zinc-400">{binningInfo.label}</span>
							<Select
								value={String(binningModel.value)}
								options={binningModel.options.map((o) => ({ value: String(o), label: `${o}x${o}` }))}
								onchange={(v) => devicesManager.setProperty(deviceId, 'binning', Number(v))}
								size="sm"
							/>
						</div>
					{/if}
				</div>
			</div>

			{#snippet frameSizeBody()}
				{#if sensorSize}
					<div class="flex justify-between">
						<span class="label">Sensor Size</span>
						<span class="value">{sensorSize.y} × {sensorSize.x} px</span>
					</div>
				{/if}
				{#if pixelSize}
					<div class="flex justify-between">
						<span class="label">Pixel Size</span>
						<span class="value">{pixelSize.y} × {pixelSize.x} µm</span>
					</div>
				{/if}
				{#if roiInfo && roiModel && Array.isArray(roiModel.value) && roiModel.value.length === 4}
					<div class="flex justify-between">
						<span class="label">ROI</span>
						<span class="value"
							>{roiModel.value[0]}, {roiModel.value[1]}, {roiModel.value[2]}, {roiModel.value[3]}</span
						>
					</div>
				{/if}
			{/snippet}

			{#snippet streamInfoBody()}
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
			{/snippet}

			{#if frameSize}
				{@const summary = `${frameSize.y} × ${frameSize.x} px${typeof frameSizeMb === 'number' ? ` | ${frameSizeMb.toFixed(2)} MB` : ''}`}
				{@render collapsible('Frame Size', summary, frameSizeBody)}
			{/if}
			{@render collapsible('Stream Info', streamInfoSummary + ' fps', streamInfoBody)}
		</div>
	{/if}
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
