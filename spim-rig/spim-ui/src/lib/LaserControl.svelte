<script lang="ts">
	import type { DevicesManager } from '$lib/devices.svelte';
	import SliderInput from '$lib/ui/SliderInput.svelte';
	import Switch from '$lib/ui/Switch.svelte';

	interface Props {
		deviceId: string;
		devicesManager: DevicesManager;
	}

	let { deviceId, devicesManager }: Props = $props();

	// Reactive device properties
	let laserDevice = $derived(devicesManager.getDevice(deviceId));
	let wavelength = $derived(devicesManager.getPropertyValue(deviceId, 'wavelength'));
	let isEnabled = $derived(devicesManager.getPropertyValue(deviceId, 'is_enabled'));
	let powerMw = $derived(devicesManager.getPropertyValue(deviceId, 'power_mw'));
	let temperatureC = $derived(devicesManager.getPropertyValue(deviceId, 'temperature_c'));
	let powerSetpointModel = $derived(devicesManager.getPropertyModel(deviceId, 'power_setpoint_mw'));
	let powerSetpointInfo = $derived(devicesManager.getPropertyInfo(deviceId, 'power_setpoint_mw'));

	function handleEnable() {
		devicesManager.executeCommand(deviceId, 'enable');
	}

	function handleDisable() {
		devicesManager.executeCommand(deviceId, 'disable');
	}

	function handleToggle(checked: boolean) {
		if (checked) {
			handleEnable();
		} else {
			handleDisable();
		}
	}

	let switchChecked = $derived(typeof isEnabled === 'boolean' ? isEnabled : false);
</script>

{#if laserDevice?.connected}
	<div class="space-y-4 rounded-lg border border-zinc-700 bg-zinc-900/70 shadow-sm">
		<!-- Laser Header -->
		<div class="flex items-center justify-between px-3 pt-3">
			<div class="text-sm font-medium text-zinc-200">
				{typeof wavelength === 'number' ? `${wavelength} nm Laser` : 'Laser'}
			</div>
			<Switch checked={switchChecked} onCheckedChange={handleToggle} />
		</div>
		<!-- Power Setpoint Slider -->
		<div class="px-3">
			{#if powerSetpointInfo && powerSetpointModel && typeof powerSetpointModel.value === 'number'}
				<SliderInput
					label={powerSetpointInfo.label}
					bind:value={powerSetpointModel.value}
					min={powerSetpointModel.min_val ?? 0}
					max={powerSetpointModel.max_val ?? 100}
					step={powerSetpointModel.step ?? 1}
					onchange={() => {
						if (typeof powerSetpointModel.value === 'number') {
							devicesManager.setProperty(deviceId, 'power_setpoint_mw', powerSetpointModel.value);
						}
					}}
				/>
			{/if}
		</div>

		<!-- Enable/Disable Controls with Status -->
		<!-- <div class="flex items-center gap-2">
			<div class="flex flex-1 gap-2">
				<button
					onclick={handleEnable}
					disabled={typeof isEnabled === 'boolean' && isEnabled}
					class="flex-1 rounded bg-emerald-600/90 px-3 py-1.5 text-xs font-medium transition-colors hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-40"
				>
					Enable
				</button>
				<button
					onclick={handleDisable}
					disabled={typeof isEnabled === 'boolean' && !isEnabled}
					class="flex-1 rounded bg-zinc-700/80 px-3 py-1.5 text-xs font-medium transition-colors hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40"
				>
					Disable
				</button>
			</div>
			{#if typeof isEnabled === 'boolean'}
				<div
					class="rounded px-2 py-1.5 text-xs font-medium {isEnabled
						? 'bg-emerald-500/20 text-emerald-400'
						: 'bg-zinc-700/50 text-zinc-500'}"
				>
					{isEnabled ? 'ON' : 'OFF'}
				</div>
			{/if}
		</div> -->
		<div class="flex items-center justify-between border-t border-zinc-700 px-3 py-2 font-mono text-xs text-zinc-300">
			{#if typeof temperatureC === 'number'}
				<div>
					{temperatureC.toFixed(1)}°C
				</div>
			{/if}
			{#if typeof powerMw === 'number'}
				<div>
					{powerMw.toFixed(1)} mW
				</div>
			{/if}
		</div>
	</div>
{:else}
	<div class="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center text-xs text-zinc-500">
		Laser not available
	</div>
{/if}
