<script lang="ts">
	import type { Session } from '$lib/main';
	import { discoverProfileDevices } from '$lib/main';
	import type { Waveform, FrameTiming } from '$lib/main';
	import type { SelectOption } from '$lib/ui/kit/Select.svelte';
	import { generateTraces, niceTicks, voltageRange } from './generate';
	import { SpinBox, Select, Button } from '$lib/ui/kit';
	import { sanitizeString } from '$lib/utils';
	import { Check, Close } from '$lib/icons';
	import { toast } from 'svelte-sonner';
	import { watch } from 'runed';
	import { SvelteSet } from 'svelte/reactivity';

	const WAVEFORM_TYPE_DEFAULTS: Record<string, Record<string, unknown>> = {
		pulse: {},
		square: { duty_cycle: 0.5 },
		sine: { frequency: 1000, phase: 0 },
		triangle: { frequency: 1000, symmetry: 0.5 },
		sawtooth: { frequency: 1000, width: 1 }
	};

	function changeWaveformType(source: Waveform, newType: string): Waveform | null {
		const extra = WAVEFORM_TYPE_DEFAULTS[newType];
		if (extra === undefined) return null;
		const base = {
			voltage: { min: source.voltage.min, max: source.voltage.max },
			window: { min: source.window.min, max: source.window.max },
			rest_voltage: source.rest_voltage
		};
		return { type: newType, ...base, ...extra } as Waveform;
	}

	function cloneWaveform(wf: Waveform): Waveform {
		const raw = structuredClone($state.snapshot(wf));
		const v = raw.voltage as Record<string, unknown>;
		const w = raw.window as Record<string, unknown>;
		delete v.span;
		delete w.span;
		return raw;
	}

	interface Props {
		session: Session;
		profileId: string;
	}

	let { session, profileId }: Props = $props();

	const profile = $derived(session.config.profiles[profileId]);
	const isActiveProfile = $derived(profileId === session.activeProfileId);
	const isIdle = $derived(session.mode === 'idle');
	const canEdit = $derived(isActiveProfile && isIdle);

	// ── DAQ hardware voltage range ──

	const daqDeviceId = $derived(session.config.daq.device);
	const daqRange = $derived.by(() => {
		const val = session.devices.getPropertyValue(daqDeviceId, 'ao_voltage_range') as
			| { min: number; max: number }
			| null
			| undefined;
		if (val && typeof val === 'object' && 'min' in val && 'max' in val) return val;
		return null;
	});

	// ── Source of truth: config waveforms ──

	const waveforms = $derived(profile?.daq.waveforms ?? {});
	const configTiming = $derived(profile?.daq.timing ?? { sample_rate: 100000, duration: 0.01, rest_time: 0 });

	// ── Waveform devices (role-sorted, with trace colors) ──

	const profileDevices = $derived(discoverProfileDevices(session.config, profileId));
	const waveformDevices = $derived(
		profileDevices.filter((d) => {
			const wf = profile?.daq.waveforms[d.id];
			return wf != null && wf.voltage != null && wf.window != null;
		})
	);
	const waveformDeviceIds = $derived(waveformDevices.map((d) => d.id));
	const waveformColors = $derived(Object.fromEntries(waveformDevices.map((d) => [d.id, d.color])));
	// ── Trace visibility ──

	let hiddenDevices = new SvelteSet<string>();

	function toggleDeviceVisibility(deviceId: string) {
		if (hiddenDevices.has(deviceId)) hiddenDevices.delete(deviceId);
		else hiddenDevices.add(deviceId);
	}

	// ── Per-device editing state (component-local, not Session) ──

	let selectedDeviceId = $state<string | null>(null);
	let editingWaveform = $state<Waveform | null>(null);

	function selectDevice(deviceId: string) {
		if (!canEdit) return;
		hiddenDevices.delete(deviceId);
		selectedDeviceId = deviceId;
		editingWaveform = cloneWaveform(waveforms[deviceId]);
	}

	function cancelEditing() {
		selectedDeviceId = null;
		editingWaveform = null;
	}

	async function commitEditing() {
		if (!selectedDeviceId || !editingWaveform) return;
		try {
			const res = await fetch(`${session.client.baseUrl}/api/rig/profile/waveforms`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ waveforms: { [selectedDeviceId]: editingWaveform } })
			});
			if (!res.ok) {
				const data = await res.json().catch(() => ({ detail: res.statusText }));
				throw new Error(data.detail || res.statusText);
			}
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to update waveform');
			return;
		}
		selectedDeviceId = null;
		editingWaveform = null;
	}

	// Clear editing when profile changes
	watch(
		() => profileId,
		() => {
			if (selectedDeviceId) {
				toast.info(`Discarded unsaved waveform changes for ${sanitizeString(selectedDeviceId)}`);
			}
			cancelEditing();
		},
		{ lazy: true }
	);

	// ── Display waveforms: merge editing draft over config for selected device ──

	const displayWaveforms = $derived.by(() => {
		if (!selectedDeviceId || !editingWaveform) return waveforms;
		return { ...waveforms, [selectedDeviceId]: editingWaveform };
	});

	// ── Timing: local state with explicit commit/cancel ──

	let localTiming = $state<FrameTiming>({ sample_rate: 100000, duration: 0.01, rest_time: 0 });
	let timingDirty = $state(false);

	// Reset local timing when config timing changes (e.g. from backend broadcast)
	watch(
		() => configTiming,
		(t) => {
			localTiming = { sample_rate: t.sample_rate, duration: t.duration, rest_time: t.rest_time };
			timingDirty = false;
		}
	);

	function updateTimingField(field: keyof FrameTiming, value: number) {
		if (!isFinite(value)) return;
		(localTiming as unknown as Record<string, unknown>)[field] = value;
		timingDirty = true;
	}

	async function commitTiming() {
		if (!canEdit || !timingDirty) return;
		try {
			const res = await fetch(`${session.client.baseUrl}/api/rig/profile/waveforms`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ timing: localTiming })
			});
			if (!res.ok) {
				const data = await res.json().catch(() => ({ detail: res.statusText }));
				throw new Error(data.detail || res.statusText);
			}
			timingDirty = false;
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Failed to update timing');
		}
	}

	function cancelTiming() {
		const t = configTiming;
		localTiming = { sample_rate: t.sample_rate, duration: t.duration, rest_time: t.rest_time };
		timingDirty = false;
	}

	// ── Derived timing values ──

	const duration = $derived(localTiming.duration ?? 0);
	const restTime = $derived(localTiming.rest_time ?? 0);
	const sampleRate = $derived(localTiming.sample_rate ?? 0);
	const frequency = $derived(duration + restTime > 0 ? 1 / (duration + restTime) : 0);
	const samples = $derived(Math.floor(sampleRate * duration));
	const totalTime = $derived(duration + restTime);

	const formatFrequency = (hz: number) => {
		if (hz >= 1_000_000) return `${(hz / 1_000_000).toFixed(2)} MHz`;
		if (hz >= 1_000) return `${(hz / 1_000).toFixed(2)} kHz`;
		return `${hz.toFixed(2)} Hz`;
	};

	// ── Waveform mutation helpers ──

	function updateEditingField(field: string, value: unknown) {
		if (!editingWaveform) return;
		if (typeof value === 'number' && !isFinite(value)) return;
		(editingWaveform as unknown as Record<string, unknown>)[field] = value;
	}

	/** Clamp a voltage to DAQ range, apply it, and snap rest_voltage into bounds. */
	function setEditingVoltage(key: 'min' | 'max', value: number) {
		if (!editingWaveform || !isFinite(value)) return;
		if (daqRange) value = Math.max(daqRange.min, Math.min(daqRange.max, value));
		editingWaveform.voltage[key] = value;
		const rest = editingWaveform.rest_voltage ?? 0;
		editingWaveform.rest_voltage = Math.max(editingWaveform.voltage.min, Math.min(editingWaveform.voltage.max, rest));
	}

	function updateEditingWindow(key: 'min' | 'max', value: number) {
		if (!editingWaveform || !isFinite(value)) return;
		editingWaveform.window[key] = value;
	}

	function changeEditingType(newType: string) {
		if (!editingWaveform || !selectedDeviceId) return;
		const result = changeWaveformType(editingWaveform, newType);
		if (result) editingWaveform = result;
	}

	const waveformTypeOptions: SelectOption[] = [
		{ value: 'pulse', label: 'Pulse' },
		{ value: 'square', label: 'Square' },
		{ value: 'sine', label: 'Sine' },
		{ value: 'triangle', label: 'Triangle' },
		{ value: 'sawtooth', label: 'Sawtooth' },
		{ value: 'multi_point', label: 'Multi-point' },
		{ value: 'csv', label: 'CSV' }
	];

	// ── Plot geometry ──

	const plotPadding = { top: 16, right: 16, bottom: 28, left: 48 };
	const plotHeight = 300;
	let plotContainerWidth = $state(600);

	const plotData = $derived(generateTraces(displayWaveforms, duration, restTime, 500));
	const plotRawRange = $derived(voltageRange(displayWaveforms));
	const plotYAxis = $derived(niceTicks(plotRawRange.min, plotRawRange.max));
	const plotVRange = $derived({ min: plotYAxis.min, max: plotYAxis.max });

	const plotW = $derived(plotContainerWidth - plotPadding.left - plotPadding.right);
	const plotH = $derived(plotHeight - plotPadding.top - plotPadding.bottom);

	function toSvgX(t: number): number {
		if (totalTime <= 0) return plotPadding.left;
		return plotPadding.left + (t / totalTime) * plotW;
	}

	function toSvgY(v: number): number {
		const denom = plotVRange.max - plotVRange.min;
		if (denom === 0 || !isFinite(v)) return plotPadding.top + plotH * 0.5;
		const frac = (v - plotVRange.min) / denom;
		return plotPadding.top + plotH * (1 - frac);
	}

	function svgXToWindowFrac(clientX: number, rect: DOMRect): number {
		const x = clientX - rect.left;
		const t = ((x - plotPadding.left) / plotW) * totalTime;
		return duration > 0 ? t / duration : 0;
	}

	function buildPath(voltages: number[]): string {
		return plotData.time
			.map((t, i) => `${i === 0 ? 'M' : 'L'}${toSvgX(t).toFixed(1)},${toSvgY(voltages[i]).toFixed(1)}`)
			.join(' ');
	}

	function formatPlotTime(s: number): string {
		if (s >= 1) return `${s.toFixed(1)}s`;
		if (s >= 0.001) return `${(s * 1000).toFixed(1)}ms`;
		return `${(s * 1e6).toFixed(0)}\u03BCs`;
	}

	function formatVoltage(v: number): string {
		return `${v.toFixed(1)}V`;
	}

	// ── SVG Drag Handles ──

	let dragging = $state<'vmin' | 'vmax' | 'wmin' | 'wmax' | null>(null);
	let frozenVRange = $state<{ min: number; max: number } | null>(null);

	function svgYToVoltageFrozen(clientY: number, rect: DOMRect): number {
		const range = frozenVRange ?? plotVRange;
		const y = clientY - rect.top;
		const frac = 1 - (y - plotPadding.top) / plotH;
		return range.min + frac * (range.max - range.min);
	}

	function onHandleDown(e: PointerEvent, handle: typeof dragging) {
		e.preventDefault();
		(e.currentTarget as SVGElement).setPointerCapture(e.pointerId);
		dragging = handle;
		if (handle === 'vmin' || handle === 'vmax') {
			frozenVRange = { min: plotVRange.min, max: plotVRange.max };
		}
	}

	function onHandleMove(e: PointerEvent) {
		if (!dragging || !editingWaveform) return;
		const svg = (e.currentTarget as SVGElement).closest('svg');
		if (!svg) return;
		const rect = svg.getBoundingClientRect();

		if (dragging === 'vmin' || dragging === 'vmax') {
			const voltage = svgYToVoltageFrozen(e.clientY, rect);
			if (dragging === 'vmin') {
				setEditingVoltage('min', Math.min(voltage, editingWaveform.voltage.max - 0.01));
			} else {
				setEditingVoltage('max', Math.max(voltage, editingWaveform.voltage.min + 0.01));
			}
		} else {
			const frac = svgXToWindowFrac(e.clientX, rect);
			if (dragging === 'wmin') {
				editingWaveform.window.min = Math.max(0, Math.min(frac, editingWaveform.window.max - 0.01));
			} else {
				editingWaveform.window.max = Math.min(1, Math.max(frac, editingWaveform.window.min + 0.01));
			}
		}
	}

	function onHandleUp(e: PointerEvent) {
		(e.currentTarget as SVGElement).releasePointerCapture(e.pointerId);
		dragging = null;
		frozenVRange = null;
	}

	// ── Handle positions (derived) ──

	const vminY = $derived(editingWaveform ? toSvgY(editingWaveform.voltage.min) : 0);
	const vmaxY = $derived(editingWaveform ? toSvgY(editingWaveform.voltage.max) : 0);
	const wminX = $derived(editingWaveform ? toSvgX(editingWaveform.window.min * duration) : 0);
	const wmaxX = $derived(editingWaveform ? toSvgX(editingWaveform.window.max * duration) : 0);

	// ── Floating input positions (anti-overlap) ──

	const floatingLabelWidth = 48;
	const floatingLabelGap = 4;

	const vLabelPositions = $derived.by(() => {
		let minTop = vminY;
		let maxTop = vmaxY;
		const minDist = 18;
		// V-max is above V-min in SVG coords (lower Y = higher voltage)
		if (minTop - maxTop < minDist) {
			const mid = (minTop + maxTop) / 2;
			maxTop = mid - minDist / 2;
			minTop = mid + minDist / 2;
		}
		// Clamp to plot area
		if (maxTop < plotPadding.top) {
			const shift = plotPadding.top - maxTop;
			maxTop += shift;
			minTop += shift;
		}
		if (minTop > plotPadding.top + plotH) {
			const shift = minTop - (plotPadding.top + plotH);
			minTop -= shift;
			maxTop -= shift;
		}
		return { minTop, maxTop };
	});

	const wLabelPositions = $derived.by(() => {
		let minLeft = wminX;
		let maxLeft = wmaxX;
		const minDist = floatingLabelWidth + floatingLabelGap;
		if (maxLeft - minLeft < minDist) {
			const mid = (minLeft + maxLeft) / 2;
			minLeft = mid - minDist / 2;
			maxLeft = mid + minDist / 2;
		}
		// Clamp to plot area
		if (minLeft < plotPadding.left) {
			const shift = plotPadding.left - minLeft;
			minLeft += shift;
			maxLeft += shift;
		}
		const rightEdge = plotPadding.left + plotW;
		if (maxLeft > rightEdge - floatingLabelWidth) {
			const shift = maxLeft - (rightEdge - floatingLabelWidth);
			maxLeft -= shift;
			minLeft -= shift;
		}
		minLeft = Math.max(plotPadding.left, minLeft);
		maxLeft = Math.min(rightEdge - floatingLabelWidth, maxLeft);
		return { minLeft, maxLeft };
	});

	// ── Handle colors ──
	const HANDLE_LINE_COLOR = '#a1a1aa'; // zinc-400 — neutral for all lines
	// Input text colors: trace color for voltage, trace color for window
	const handleInputColors = $derived.by(() => {
		const traceColor = selectedDeviceId ? (waveformColors[selectedDeviceId] ?? '#a1a1aa') : '#a1a1aa';
		return { vmin: traceColor, vmax: traceColor, wmin: traceColor, wmax: traceColor };
	});

	// ── Applied traces (server-computed voltage arrays, ground truth) ──
	const appliedTraces = $derived.by(() => {
		if (!session.appliedWaveforms?.traces) return null;
		const wfs = session.appliedWaveforms.traces;
		const firstVoltages = Object.values(wfs)[0];
		if (!firstVoltages?.length) return null;
		const n = firstVoltages.length;
		const dt = totalTime / (n - 1);
		const time = Array.from({ length: n }, (_, i) => i * dt);
		return { time, wfs };
	});

	function buildAppliedPath(voltages: number[], time: number[]): string {
		return time
			.map((t, i) => `${i === 0 ? 'M' : 'L'}${toSvgX(t).toFixed(1)},${toSvgY(voltages[i]).toFixed(1)}`)
			.join(' ');
	}
</script>

{#if profile}
	<div class="flex flex-col gap-0 rounded border bg-card shadow-sm">
		<!-- ═══ HEADER: Timing controls ═══ -->
		<div class="flex h-10 items-center gap-3 border-b px-3">
			<SpinBox
				value={sampleRate}
				prefix="Sample Rate"
				suffix=" Hz"
				size="xs"
				appearance="full"
				numCharacters={8}
				align="right"
				step={1000}
				min={1}
				disabled={!canEdit}
				onChange={(v) => updateTimingField('sample_rate', v)}
			/>
			<SpinBox
				value={duration}
				prefix="Duration"
				suffix=" s"
				size="xs"
				appearance="full"
				decimals={4}
				numCharacters={8}
				align="right"
				step={0.001}
				min={0.0001}
				disabled={!canEdit}
				onChange={(v) => updateTimingField('duration', v)}
			/>
			<SpinBox
				value={restTime}
				prefix="Rest Time"
				suffix=" s"
				size="xs"
				appearance="full"
				decimals={4}
				numCharacters={8}
				align="right"
				step={0.001}
				min={0}
				disabled={!canEdit}
				onChange={(v) => updateTimingField('rest_time', v)}
			/>
			{#if timingDirty && canEdit}
				<div class="flex gap-1">
					<Button variant="ghost" size="sm" onclick={cancelTiming} title="Reset timing">
						<Close width="12" height="12" />
					</Button>
					<Button variant="outline" size="sm" onclick={commitTiming} title="Apply timing">
						<Check width="12" height="12" />
					</Button>
				</div>
			{/if}
			<div class="text-fg-muted ml-auto flex gap-4 text-xs">
				<span>Freq <span class="text-fg font-mono">{formatFrequency(frequency)}</span></span>
				<span>Samples <span class="text-fg font-mono">{samples.toLocaleString()}</span></span>
			</div>
		</div>

		<!-- ═══ MAIN: Sidebar + Plot ═══ -->
		<div class="flex">
			<!-- Sidebar: Device list -->
			<div class="flex w-28 shrink-0 flex-col gap-0.5 border-r px-2 py-2">
				{#each waveformDeviceIds as deviceId (deviceId)}
					{@const isSelected = deviceId === selectedDeviceId}
					{@const isHidden = hiddenDevices.has(deviceId)}
					<div
						class="text-fg-muted flex items-center gap-1.5 rounded px-1.5 py-1 text-xs transition-colors
							{isSelected ? 'bg-element-selected text-fg' : ''}"
					>
						<button
							type="button"
							class="h-2 w-2 shrink-0 rounded-full {isSelected ? '' : 'cursor-pointer'}"
							style={isHidden
								? `border: 1px solid ${waveformColors[deviceId]}; background: transparent;`
								: `background-color: ${waveformColors[deviceId]};`}
							onclick={() => toggleDeviceVisibility(deviceId)}
							disabled={isSelected}
							title={isHidden ? 'Show trace' : 'Hide trace'}
						></button>
						<button
							type="button"
							class="truncate text-left transition-colors
								{isSelected ? 'text-fg' : canEdit ? 'hover:text-fg cursor-pointer' : ''}"
							onclick={() => {
								if (canEdit) {
									if (isSelected) cancelEditing();
									else selectDevice(deviceId);
								}
							}}
							disabled={!canEdit}
						>
							{sanitizeString(deviceId)}
						</button>
					</div>
				{/each}
			</div>

			<!-- Plot area -->
			<div class="relative min-w-0 flex-1 overflow-hidden px-2 py-2" bind:clientWidth={plotContainerWidth}>
				{#if waveformDeviceIds.length > 0 && duration > 0}
					<!-- Floating voltage inputs (V-min / V-max) -->
					{#if editingWaveform && selectedDeviceId}
						<input
							type="text"
							class="handle-input"
							style="position:absolute; right:4px; top:{vLabelPositions.maxTop - 7}px; color:{handleInputColors.vmax};"
							value="{editingWaveform.voltage.max.toFixed(2)} V"
							onchange={(e) => {
								const v = parseFloat((e.target as HTMLInputElement).value);
								if (!isNaN(v)) setEditingVoltage('max', v);
							}}
						/>
						<input
							type="text"
							class="handle-input"
							style="position:absolute; right:4px; top:{vLabelPositions.minTop - 7}px; color:{handleInputColors.vmin};"
							value="{editingWaveform.voltage.min.toFixed(2)} V"
							onchange={(e) => {
								const v = parseFloat((e.target as HTMLInputElement).value);
								if (!isNaN(v)) setEditingVoltage('min', v);
							}}
						/>
						<!-- Floating window inputs (W-min / W-max) — top to avoid x-axis labels -->
						<input
							type="text"
							class="handle-input text-left"
							style="position:absolute; top:2px; left:{wLabelPositions.minLeft}px; color:{handleInputColors.wmin};"
							value={editingWaveform.window.min.toFixed(2)}
							onchange={(e) => {
								const v = parseFloat((e.target as HTMLInputElement).value);
								if (!isNaN(v)) updateEditingWindow('min', Math.max(0, Math.min(1, v)));
							}}
						/>
						<input
							type="text"
							class="handle-input text-left"
							style="position:absolute; top:2px; left:{wLabelPositions.maxLeft}px; color:{handleInputColors.wmax};"
							value={editingWaveform.window.max.toFixed(2)}
							onchange={(e) => {
								const v = parseFloat((e.target as HTMLInputElement).value);
								if (!isNaN(v)) updateEditingWindow('max', Math.max(0, Math.min(1, v)));
							}}
						/>
					{/if}

					<svg width="100%" height={plotHeight} viewBox="0 0 {plotContainerWidth} {plotHeight}" class="select-none">
						<!-- Horizontal grid + Y-axis labels -->
						{#each plotYAxis.ticks as v (v)}
							{@const y = toSvgY(v)}
							<line
								x1={plotPadding.left}
								y1={y}
								x2={plotPadding.left + plotW}
								y2={y}
								class="stroke-border"
								stroke-width="1"
							/>
							<text
								x={plotPadding.left - 6}
								{y}
								text-anchor="end"
								dominant-baseline="middle"
								class="fill-fg-muted text-xs"
							>
								{formatVoltage(v)}
							</text>
						{/each}

						<!-- DAQ hardware voltage limit lines -->
						{#if daqRange}
							{#if daqRange.min >= plotVRange.min && daqRange.min <= plotVRange.max}
								{@const y = toSvgY(daqRange.min)}
								<line
									x1={plotPadding.left}
									y1={y}
									x2={plotPadding.left + plotW}
									y2={y}
									stroke="#ef4444"
									stroke-width="1"
									stroke-dasharray="6 3"
									opacity="0.4"
								/>
								<text x={plotPadding.left + 4} y={y - 3} class="text-xs" fill="#ef4444" opacity="0.6"> DAQ min </text>
							{/if}
							{#if daqRange.max >= plotVRange.min && daqRange.max <= plotVRange.max}
								{@const y = toSvgY(daqRange.max)}
								<line
									x1={plotPadding.left}
									y1={y}
									x2={plotPadding.left + plotW}
									y2={y}
									stroke="#ef4444"
									stroke-width="1"
									stroke-dasharray="6 3"
									opacity="0.4"
								/>
								<text x={plotPadding.left + 4} y={y + 10} class="text-xs" fill="#ef4444" opacity="0.6"> DAQ max </text>
							{/if}
						{/if}

						<!-- Rest region indicator -->
						{#if restTime > 0}
							{@const restX = toSvgX(duration)}
							<rect
								x={restX}
								y={plotPadding.top}
								width={Math.max(0, plotPadding.left + plotW - restX)}
								height={plotH}
								class="fill-muted/70"
							/>
						{/if}

						<!-- X-axis labels -->
						{#each [0, 0.25, 0.5, 0.75, 1] as frac (frac)}
							{@const t = frac * totalTime}
							{@const x = toSvgX(t)}
							<text {x} y={plotHeight - 4} text-anchor="middle" class="fill-fg-muted text-xs">
								{formatPlotTime(t)}
							</text>
						{/each}

						<!-- ═══ Handle visible lines ═══ -->
						{#if editingWaveform && selectedDeviceId}
							<g stroke={HANDLE_LINE_COLOR} stroke-width="1" stroke-dasharray="4 2" pointer-events="none">
								<line x1={plotPadding.left} y1={vminY} x2={plotPadding.left + plotW} y2={vminY} />
								<line x1={plotPadding.left} y1={vmaxY} x2={plotPadding.left + plotW} y2={vmaxY} />
								<line x1={wminX} y1={plotPadding.top} x2={wminX} y2={plotPadding.top + plotH} />
								<line x1={wmaxX} y1={plotPadding.top} x2={wmaxX} y2={plotPadding.top + plotH} />
							</g>
						{/if}

						<!-- Applied traces (behind config, only for active profile) -->
						{#if isActiveProfile && appliedTraces}
							{#each waveformDeviceIds as deviceId (deviceId)}
								{@const voltages = appliedTraces.wfs[deviceId]}
								{@const isSelected = deviceId === selectedDeviceId}
								{#if voltages && !hiddenDevices.has(deviceId)}
									<path
										d={buildAppliedPath(voltages, appliedTraces.time)}
										fill="none"
										stroke={waveformColors[deviceId] ?? '#888'}
										stroke-width="1"
										stroke-linejoin="round"
										stroke-dasharray="4 2"
										opacity={!selectedDeviceId ? 0.3 : isSelected ? 0.5 : 0.15}
									/>
								{/if}
							{/each}
						{/if}

						<!-- Config traces (primary visualization, always visible) -->
						{#each waveformDeviceIds as deviceId (deviceId)}
							{@const voltages = plotData.traces[deviceId]}
							{@const isSelected = deviceId === selectedDeviceId}
							{#if voltages && !hiddenDevices.has(deviceId)}
								<path
									d={buildPath(voltages)}
									fill="none"
									stroke={waveformColors[deviceId] ?? '#888'}
									stroke-width={isSelected && editingWaveform ? 1.5 : 1}
									stroke-linejoin="round"
									opacity={!selectedDeviceId ? 0.75 : isSelected ? 0.6 : 0.3}
								/>
							{/if}
						{/each}

						<!-- ═══ Handle hit targets (above traces for pointer events) ═══ -->
						{#if editingWaveform && selectedDeviceId}
							<g stroke="transparent" stroke-width="12">
								<g class="cursor-ns-resize">
									<line
										x1={plotPadding.left}
										y1={vminY}
										x2={plotPadding.left + plotW}
										y2={vminY}
										onpointerdown={(e) => onHandleDown(e, 'vmin')}
										onpointermove={onHandleMove}
										onpointerup={onHandleUp}
										role="slider"
										tabindex="0"
										aria-label="Voltage minimum"
										aria-valuenow={editingWaveform?.voltage.min ?? 0}
									/>
									<line
										x1={plotPadding.left}
										y1={vmaxY}
										x2={plotPadding.left + plotW}
										y2={vmaxY}
										onpointerdown={(e) => onHandleDown(e, 'vmax')}
										onpointermove={onHandleMove}
										onpointerup={onHandleUp}
										role="slider"
										tabindex="0"
										aria-label="Voltage maximum"
										aria-valuenow={editingWaveform?.voltage.max ?? 0}
									/>
								</g>
								<g class="cursor-ew-resize">
									<line
										x1={wminX}
										y1={plotPadding.top}
										x2={wminX}
										y2={plotPadding.top + plotH}
										onpointerdown={(e) => onHandleDown(e, 'wmin')}
										onpointermove={onHandleMove}
										onpointerup={onHandleUp}
										role="slider"
										tabindex="0"
										aria-label="Window minimum"
										aria-valuenow={editingWaveform?.window.min ?? 0}
									/>
									<line
										x1={wmaxX}
										y1={plotPadding.top}
										x2={wmaxX}
										y2={plotPadding.top + plotH}
										onpointerdown={(e) => onHandleDown(e, 'wmax')}
										onpointermove={onHandleMove}
										onpointerup={onHandleUp}
										role="slider"
										tabindex="0"
										aria-label="Window maximum"
										aria-valuenow={editingWaveform?.window.max ?? 0}
									/>
								</g>
							</g>
						{/if}
					</svg>
				{:else}
					<div class="flex items-center justify-center" style:height="{plotHeight}px">
						<span class="text-fg-muted text-sm">No waveform data</span>
					</div>
				{/if}
			</div>
		</div>

		<!-- ═══ FOOTER: Device editor ═══ -->
		<div class="border-t px-3 py-2">
			{#if editingWaveform && selectedDeviceId && canEdit}
				{@const wf = editingWaveform}
				<div class="flex flex-wrap items-end gap-3">
					<!-- Type selector -->
					<div class="w-24">
						<Select size="xs" value={wf.type} options={waveformTypeOptions} onchange={(v) => changeEditingType(v)} />
					</div>

					<SpinBox
						value={wf.rest_voltage ?? 0}
						prefix="Rest V"
						suffix=" V"
						size="xs"
						appearance="full"
						decimals={2}
						step={0.1}
						min={wf.voltage.min}
						max={wf.voltage.max}
						snapValue={() => wf.voltage.min}
						numCharacters={6}
						align="right"
						onChange={(v) => updateEditingField('rest_voltage', v)}
					/>

					<!-- Type-specific fields -->
					{#if wf.type === 'square'}
						<SpinBox
							value={wf.duty_cycle}
							prefix="Duty"
							min={0}
							max={1}
							step={0.05}
							size="xs"
							appearance="full"
							decimals={2}
							numCharacters={6}
							align="right"
							onChange={(v) => updateEditingField('duty_cycle', v)}
						/>
					{/if}
					{#if wf.type === 'square' || wf.type === 'sine' || wf.type === 'triangle' || wf.type === 'sawtooth'}
						<SpinBox
							value={wf.frequency ?? 0}
							prefix="Freq"
							suffix=" Hz"
							size="xs"
							appearance="full"
							step={1}
							min={0}
							numCharacters={8}
							align="right"
							onChange={(v) => updateEditingField('frequency', v)}
						/>
					{/if}
					{#if wf.type === 'sine'}
						<SpinBox
							value={(wf.phase ?? 0) * (180 / Math.PI)}
							prefix="Phase"
							suffix=" deg"
							size="xs"
							appearance="full"
							step={5}
							numCharacters={6}
							align="right"
							onChange={(v) => updateEditingField('phase', v * (Math.PI / 180))}
						/>
					{/if}
					{#if wf.type === 'triangle'}
						<SpinBox
							value={wf.symmetry ?? 0.5}
							prefix="Symmetry"
							min={0}
							max={1}
							step={0.05}
							size="xs"
							appearance="full"
							decimals={2}
							numCharacters={6}
							align="right"
							onChange={(v) => updateEditingField('symmetry', v)}
						/>
					{/if}
					{#if wf.type === 'sawtooth'}
						<SpinBox
							value={wf.width ?? 1}
							prefix="Width"
							min={0}
							max={1}
							step={0.05}
							size="xs"
							appearance="full"
							decimals={2}
							numCharacters={6}
							align="right"
							onChange={(v) => updateEditingField('width', v)}
						/>
					{/if}

					<!-- Commit / Cancel -->
					<div class="ml-auto flex gap-1.5">
						<Button variant="ghost" size="sm" onclick={cancelEditing} title="Cancel">
							<Close width="14" height="14" />
						</Button>
						<Button variant="outline" size="sm" onclick={commitEditing} title="Apply changes">
							<Check width="14" height="14" />
						</Button>
					</div>
				</div>
			{:else if canEdit}
				<span class="text-fg-muted text-xs">Select a device to edit its waveform</span>
			{:else}
				<span class="text-xs text-warning/50">
					{!isActiveProfile
						? 'Activate profile to edit timing and waveforms'
						: 'Stop preview to edit timing and waveforms'}
				</span>
			{/if}
		</div>
	</div>
{/if}

<style>
	.handle-input {
		width: 48px;
		font-family: var(--font-mono, ui-monospace, monospace);
		font-size: 0.6rem;
		line-height: 1;
		background: transparent;
		border: 1px solid transparent;
		border-radius: 2px;
		outline: none;
		padding: 1px 2px;
		user-select: none;
		transition: border-color 0.15s ease;
		z-index: 10;
	}

	.handle-input:hover {
		border-color: var(--color-input);
	}

	.handle-input:focus {
		border-color: var(--color-ring);
	}
</style>
