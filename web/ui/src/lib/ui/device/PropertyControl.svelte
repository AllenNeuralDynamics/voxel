<script lang="ts">
	import type { DevicesManager } from '$lib/main';
	import { JsonView, Select, Switch, SpinBox, TextInput } from '$lib/ui/kit';
	import SliderInput from './SliderInput.svelte';
	import { isStructuredValue } from './utils';

	interface Props {
		deviceId: string;
		propName: string;
		devicesManager: DevicesManager;
		size?: 'sm' | 'md';
	}

	let { deviceId, propName, devicesManager, size = 'sm' }: Props = $props();

	let info = $derived(devicesManager.getPropertyInfo(deviceId, propName));
	let model = $derived(devicesManager.getPropertyModel(deviceId, propName));

	const NUMERIC_DTYPES = new Set(['int', 'float', 'number']);

	// Strip " | none" from union dtypes so "float | none" → "float"
	let baseDtype = $derived(info ? (info.dtype.split(' | ').find((t) => t !== 'none') ?? info.dtype) : '');

	let isNumeric = $derived(NUMERIC_DTYPES.has(baseDtype));
	let hasBounds = $derived(model?.min_val != null && model?.max_val != null);
	let hasOptions = $derived(model?.options != null && Array.isArray(model.options) && model.options.length > 0);
	let isReadonly = $derived(info?.access === 'ro');

	function formatValue(value: unknown, units?: string): string {
		if (value == null) return '\u2014';
		if (typeof value === 'number') {
			const num = Number.isInteger(value) ? String(value) : value.toFixed(2);
			return units ? `${num} ${units}` : num;
		}
		if (typeof value === 'boolean') return value ? 'Yes' : 'No';
		if (typeof value !== 'object' || value === null) return String(value);
		// FrameRegion: { x, y, width, height } — check before Vec2D since it also has x,y
		if ('width' in value && 'height' in value) {
			const r = value as { x: number; y: number; width: number; height: number };
			return `${r.width}\u00d7${r.height} @ (${r.x}, ${r.y})`;
		}
		// Vec2D / IVec2D: { y, x }
		if ('y' in value && 'x' in value) {
			const v = value as { y: number; x: number };
			const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2));
			const text = `${fmt(v.y)} \u00d7 ${fmt(v.x)}`;
			return units ? `${text} ${units}` : text;
		}
		// Generic object: compact inline for small flat objects
		const entries = Object.entries(value as Record<string, unknown>);
		return entries.map(([k, v]) => `${k}: ${formatValue(v)}`).join(', ');
	}

	let isStructured = $derived(isStructuredValue(model?.value));
</script>

{#if info && model}
	{#if isReadonly}
		<!-- Read-only display -->
		{#if isStructured}
			<JsonView data={model.value} />
		{:else}
			<span class="text-fg-muted font-mono text-sm">
				{formatValue(model.value, info.units || undefined)}
			</span>
		{/if}
	{:else if hasOptions}
		<!-- Enumerated options → Select -->
		<Select
			value={String(model.value ?? '')}
			options={model.options!.map((o) => ({ value: String(o), label: String(o) }))}
			onchange={(v) => {
				const parsed = isNumeric ? Number(v) : v;
				devicesManager.setProperty(deviceId, propName, parsed);
			}}
			{size}
		/>
	{:else if baseDtype === 'bool' && typeof model.value === 'boolean'}
		<!-- Boolean → Switch -->
		<Switch
			checked={model.value}
			onCheckedChange={(checked) => devicesManager.setProperty(deviceId, propName, checked)}
			size="sm"
		/>
	{:else if isNumeric && hasBounds && typeof model.value === 'number'}
		<!-- Bounded numeric → SliderInput -->
		<SliderInput
			label=""
			bind:target={model.value}
			min={model.min_val ?? 0}
			max={model.max_val ?? 100}
			step={model.step ?? 1}
			onChange={(v) => devicesManager.setProperty(deviceId, propName, v)}
		/>
	{:else if isNumeric && typeof model.value === 'number'}
		<!-- Unbounded numeric → SpinBox -->
		<SpinBox
			bind:value={model.value}
			min={model.min_val ?? undefined}
			max={model.max_val ?? undefined}
			step={model.step ?? 1}
			suffix={info.units ? ` ${info.units}` : undefined}
			onChange={(v) => devicesManager.setProperty(deviceId, propName, v)}
			numCharacters={12}
			appearance="full"
			{size}
		/>
	{:else if baseDtype === 'str' && typeof model.value === 'string'}
		<!-- String → TextInput -->
		<TextInput value={model.value} onChange={(v) => devicesManager.setProperty(deviceId, propName, v)} {size} />
	{:else}
		<!-- Fallback: formatted display -->
		{#if isStructured}
			<JsonView data={model.value} />
		{:else}
			<span class="text-fg-muted font-mono text-sm">
				{formatValue(model.value, info.units || undefined)}
			</span>
		{/if}
	{/if}
{/if}
