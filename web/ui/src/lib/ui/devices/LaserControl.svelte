<script lang="ts">
	import type { DevicesManager } from '$lib/main';
	import SliderInput from '$lib/ui/primitives/SliderInput.svelte';
	import Switch from '$lib/ui/primitives/Switch.svelte';

	interface Props {
		deviceId: string;
		devicesManager: DevicesManager;
		collapsed?: boolean;
	}

	let { deviceId, devicesManager, collapsed = false }: Props = $props();

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
	{#if collapsed}
		<div class="flex items-center justify-between py-1 font-mono text-[0.6rem] text-zinc-300">
			<span class="text-zinc-400/90">
				{typeof wavelength === 'number' ? `${wavelength} nm` : 'Laser'}
			</span>
			<div class="flex items-center">
				{#if typeof powerMw === 'number'}
					<span>{powerMw.toFixed(1)} mW</span>
				{/if}
				<div class="ml-3 h-1.5 w-1.5 rounded-full {switchChecked ? 'bg-emerald-500' : 'bg-zinc-600'}"></div>
			</div>
		</div>
	{:else}
		<div class="space-y-2 rounded-lg border border-zinc-700 bg-zinc-800/80 shadow-sm">
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
						onChange={(newValue) => {
							devicesManager.setProperty(deviceId, 'power_setpoint_mw', newValue);
						}}
					/>
				{/if}
			</div>

			<div
				class="flex items-center justify-between border-t border-zinc-700 px-3 py-2 font-mono text-xs text-zinc-300"
			>
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
	{/if}
{:else}
	<div class="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center text-xs text-zinc-500">
		Laser not available
	</div>
{/if}
