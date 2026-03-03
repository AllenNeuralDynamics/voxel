<script lang="ts">
	import { untrack, type Snippet } from 'svelte';
	import type { Waveform } from '$lib/main';
	import { generateTraces, voltageRange } from './generate';

	interface Props {
		waveforms: Record<string, Waveform>;
		duration: number;
		restTime: number;
		colors?: Record<string, string>;
		numPoints?: number;
		height?: number;
		footerLeft?: Snippet;
	}

	let { waveforms, duration, restTime, colors = {}, numPoints = 500, height = 200, footerLeft }: Props = $props();

	let layerVisibility = $state<Record<string, boolean>>({});

	$effect(() => {
		const keys = Object.keys(waveforms);
		untrack(() => {
			const next: Record<string, boolean> = {};
			for (const k of keys) {
				next[k] = layerVisibility[k] ?? true;
			}
			layerVisibility = next;
		});
	});

	function toggleLayer(deviceId: string) {
		layerVisibility = { ...layerVisibility, [deviceId]: !layerVisibility[deviceId] };
	}

	const padding = { top: 12, right: 16, bottom: 28, left: 48 };

	const data = $derived(generateTraces(waveforms, duration, restTime, numPoints));
	const vRange = $derived(voltageRange(waveforms));
	const totalTime = $derived(duration + restTime);

	const visibleIds = $derived(Object.keys(waveforms).filter((id) => layerVisibility[id] !== false));

	const defaultColors = [
		'var(--color-chart-1)',
		'var(--color-chart-2)',
		'var(--color-chart-3)',
		'var(--color-chart-4)',
		'var(--color-chart-5)'
	];

	function colorFor(deviceId: string, idx: number): string {
		return colors[deviceId] ?? defaultColors[idx % defaultColors.length];
	}

	function toSvgX(t: number, width: number): number {
		return padding.left + (t / totalTime) * (width - padding.left - padding.right);
	}

	function toSvgY(v: number): number {
		const plotH = height - padding.top - padding.bottom;
		const frac = (v - vRange.min) / (vRange.max - vRange.min);
		return padding.top + plotH * (1 - frac);
	}

	function buildPath(voltages: number[], width: number): string {
		return data.time
			.map((t, i) => `${i === 0 ? 'M' : 'L'}${toSvgX(t, width).toFixed(1)},${toSvgY(voltages[i]).toFixed(1)}`)
			.join(' ');
	}

	/** Format seconds for axis labels. */
	function formatTime(s: number): string {
		if (s >= 1) return `${s.toFixed(1)}s`;
		if (s >= 0.001) return `${(s * 1000).toFixed(1)}ms`;
		return `${(s * 1e6).toFixed(0)}μs`;
	}

	function formatVoltage(v: number): string {
		return `${v.toFixed(1)}V`;
	}

	let containerWidth = $state(600);

	const plotW = $derived(containerWidth - padding.left - padding.right);
	const plotH = $derived(height - padding.top - padding.bottom);
</script>

<div class="flex w-full flex-col" bind:clientWidth={containerWidth}>
	<svg width={containerWidth} {height} viewBox="0 0 {containerWidth} {height}" class="select-none">
		<!-- Horizontal grid + Y-axis labels -->
		{#each Array.from({ length: 5 }, (_, i) => vRange.min + ((vRange.max - vRange.min) * i) / 4) as v (v)}
			{@const y = toSvgY(v)}
			<line x1={padding.left} y1={y} x2={padding.left + plotW} y2={y} class="stroke-border" stroke-width="1" />
			<text
				x={padding.left - 6}
				{y}
				text-anchor="end"
				dominant-baseline="middle"
				class="fill-muted-foreground text-[0.55rem]"
			>
				{formatVoltage(v)}
			</text>
		{/each}

		<!-- Rest region indicator -->
		{#if restTime > 0}
			{@const restX = toSvgX(duration, containerWidth)}
			<rect x={restX} y={padding.top} width={padding.left + plotW - restX} height={plotH} class="fill-muted/30" />
		{/if}

		<!-- X-axis labels -->
		{#each [0, 0.25, 0.5, 0.75, 1] as frac (frac)}
			{@const t = frac * totalTime}
			{@const x = toSvgX(t, containerWidth)}
			<text {x} y={height - 4} text-anchor="middle" class="fill-muted-foreground text-[0.55rem]">
				{formatTime(t)}
			</text>
		{/each}

		<!-- Waveform traces -->
		{#each visibleIds as deviceId, idx (deviceId)}
			{@const voltages = data.traces[deviceId]}
			{#if voltages}
				<path
					d={buildPath(voltages, containerWidth)}
					fill="none"
					stroke={colorFor(deviceId, idx)}
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
			{/if}
		{/each}
	</svg>

	<!-- Footer: optional left content + toggle chips right -->
	<div class="flex items-center gap-3 border-t px-3 py-2">
		{#if footerLeft}
			{@render footerLeft()}
		{/if}
		<div class="ml-auto flex flex-wrap items-center gap-1.5">
			{#each Object.keys(waveforms) as deviceId, idx (deviceId)}
				{@const visible = layerVisibility[deviceId] !== false}
				<button
					type="button"
					class="flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.6rem] transition-colors hover:bg-muted"
					onclick={() => toggleLayer(deviceId)}
				>
					<span
						class="inline-block h-2 w-2 shrink-0 rounded-full {visible ? '' : 'opacity-30'}"
						style="background-color: {colorFor(deviceId, idx)}"
					></span>
					<span class={visible ? 'text-foreground' : 'text-muted-foreground/50'}>{deviceId}</span>
				</button>
			{/each}
		</div>
	</div>
</div>
