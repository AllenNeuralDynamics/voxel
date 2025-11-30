<script lang="ts">
	import type { RigManager } from '$lib/core';

	interface Props {
		manager: RigManager;
	}

	let { manager }: Props = $props();

	// Get stage configuration
	let stageConfig = $derived(manager.config?.stage);

	// Helper to get axis display data
	function getAxisData(deviceId: string | null | undefined) {
		if (!deviceId) return null;

		const device = manager.devices.getDevice(deviceId);
		if (!device?.connected) return null;

		const position = manager.devices.getPropertyValue(deviceId, 'position_mm');
		const isMoving = manager.devices.getPropertyValue(deviceId, 'is_moving');

		return {
			position: typeof position === 'number' ? position : null,
			isMoving: typeof isMoving === 'boolean' ? isMoving : false
		};
	}

	// Derived data for each axis
	let xData = $derived(getAxisData(stageConfig?.x));
	let yData = $derived(getAxisData(stageConfig?.y));
	let zData = $derived(getAxisData(stageConfig?.z));
	let rollData = $derived(getAxisData(stageConfig?.roll));
	let pitchData = $derived(getAxisData(stageConfig?.pitch));
	let yawData = $derived(getAxisData(stageConfig?.yaw));

	// Format position with explicit sign
	function formatPosition(position: number | null): string {
		if (position === null) return '---';
		const formatted = Math.abs(position).toFixed(2);
		return position >= 0 ? `+${formatted}` : `-${formatted}`;
	}
</script>

{#if stageConfig}
	<div class="flex items-center gap-3 font-mono text-xs text-zinc-400">
		<span class="text-zinc-500">Stage:</span>

		<!-- X Axis -->
		{#if xData}
			<div class="flex items-center gap-1.5">
				<span class="text-zinc-500">X:</span>
				<span class="text-zinc-300">{formatPosition(xData.position)}</span>
				<div class="h-1.5 w-1.5 rounded-full {xData.isMoving ? 'bg-emerald-500' : 'bg-zinc-600'}"></div>
			</div>
		{/if}

		<!-- Y Axis -->
		{#if yData}
			<div class="flex items-center gap-1.5">
				<span class="text-zinc-500">Y:</span>
				<span class="text-zinc-300">{formatPosition(yData.position)}</span>
				<div class="h-1.5 w-1.5 rounded-full {yData.isMoving ? 'bg-emerald-500' : 'bg-zinc-600'}"></div>
			</div>
		{/if}

		<!-- Z Axis -->
		{#if zData}
			<div class="flex items-center gap-1.5">
				<span class="text-zinc-500">Z:</span>
				<span class="text-zinc-300">{formatPosition(zData.position)}</span>
				<div class="h-1.5 w-1.5 rounded-full {zData.isMoving ? 'bg-emerald-500' : 'bg-zinc-600'}"></div>
			</div>
		{/if}

		<!-- Optional rotation axes -->
		{#if rollData || pitchData || yawData}
			<span class="text-zinc-600">|</span>
		{/if}

		<!-- Roll Axis -->
		{#if rollData}
			<div class="flex items-center gap-1.5">
				<span class="text-zinc-500">Roll:</span>
				<span class="text-zinc-300">{formatPosition(rollData.position)}</span>
				<div class="h-1.5 w-1.5 rounded-full {rollData.isMoving ? 'bg-emerald-500' : 'bg-zinc-600'}"></div>
			</div>
		{/if}

		<!-- Pitch Axis -->
		{#if pitchData}
			<div class="flex items-center gap-1.5">
				<span class="text-zinc-500">Pitch:</span>
				<span class="text-zinc-300">{formatPosition(pitchData.position)}</span>
				<div class="h-1.5 w-1.5 rounded-full {pitchData.isMoving ? 'bg-emerald-500' : 'bg-zinc-600'}"></div>
			</div>
		{/if}

		<!-- Yaw Axis -->
		{#if yawData}
			<div class="flex items-center gap-1.5">
				<span class="text-zinc-500">Yaw:</span>
				<span class="text-zinc-300">{formatPosition(yawData.position)}</span>
				<div class="h-1.5 w-1.5 rounded-full {yawData.isMoving ? 'bg-emerald-500' : 'bg-zinc-600'}"></div>
			</div>
		{/if}
	</div>
{/if}
