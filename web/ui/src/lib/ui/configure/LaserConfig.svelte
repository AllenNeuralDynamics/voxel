<script lang="ts">
	import type { Session } from '$lib/main';
	import { cn, sanitizeString, wavelengthToColor } from '$lib/utils';
	import SliderInput from '$lib/ui/SliderInput.svelte';
	import { Switch } from '$lib/ui/kit';
	import DynamicProperties from './DynamicProperties.svelte';
	import { laser as laserExclusions } from './utils';

	interface Props {
		session: Session;
		deviceId: string;
	}

	let { session, deviceId }: Props = $props();

	let devicesManager = $derived(session.devices);
	let device = $derived(devicesManager.getDevice(deviceId));

	// Hand-crafted property bindings
	let wavelength = $derived(devicesManager.getPropertyValue(deviceId, 'wavelength'));
	let laserColor = $derived(wavelengthToColor(typeof wavelength === 'number' ? wavelength : undefined));
	let isEnabled = $derived(devicesManager.getPropertyValue(deviceId, 'is_enabled'));
	let powerMw = $derived(devicesManager.getPropertyValue(deviceId, 'power_mw'));
	let temperatureC = $derived(devicesManager.getPropertyValue(deviceId, 'temperature_c'));
	let powerSetpointModel = $derived(devicesManager.getPropertyModel(deviceId, 'power_setpoint_mw'));
	let powerSetpointInfo = $derived(devicesManager.getPropertyInfo(deviceId, 'power_setpoint_mw'));

	let switchChecked = $derived(typeof isEnabled === 'boolean' ? isEnabled : false);

	function handleToggle(checked: boolean) {
		devicesManager.fireCommand(deviceId, checked ? 'enable' : 'disable');
	}
</script>

<section class="space-y-6">
	<!-- Header with enable switch -->
	<div class="flex items-center justify-between">
		<div class="flex items-center gap-2">
			<span class="h-2.5 w-2.5 rounded-full" style="background-color: {laserColor}"></span>
			<h2 class="text-sm font-medium text-foreground">
				{typeof wavelength === 'number' ? `${wavelength} nm Laser` : sanitizeString(deviceId)}
			</h2>
		</div>
		<div class="flex items-center gap-3">
			<span
				class={cn('h-2 w-2 rounded-full', device?.connected ? 'bg-success' : 'bg-muted-foreground/30')}
				title={device?.connected ? 'Connected' : 'Disconnected'}
			></span>
			{#if device?.connected}
				<Switch
					checked={switchChecked}
					onCheckedChange={handleToggle}
					size="sm"
					style="--switch-accent: {laserColor}"
				/>
			{/if}
		</div>
	</div>

	{#if device?.connected}
		<div class="max-w-xl space-y-6">
			<!-- Power Setpoint -->
			{#if powerSetpointInfo && powerSetpointModel && typeof powerSetpointModel.value === 'number'}
				<div>
					<SliderInput
						label={powerSetpointInfo.label}
						bind:target={powerSetpointModel.value}
						readback={typeof powerMw === 'number' ? powerMw : undefined}
						min={powerSetpointModel.min_val ?? 0}
						max={powerSetpointModel.max_val ?? 100}
						step={powerSetpointModel.step ?? 1}
						onChange={(v) => devicesManager.setProperty(deviceId, 'power_setpoint_mw', v)}
					/>
				</div>
			{/if}

			<!-- Status readback -->
			{#if typeof powerMw === 'number' || typeof temperatureC === 'number'}
				<div class="rounded border border-border bg-card p-3">
					<h4 class="mb-2 text-[0.65rem] font-medium tracking-wide text-muted-foreground uppercase">Status</h4>
					<div class="grid gap-1.5 text-xs">
						{#if typeof powerMw === 'number'}
							<div class="flex justify-between">
								<span class="text-muted-foreground">Power</span>
								<span class="font-mono text-foreground">{powerMw.toFixed(1)} mW</span>
							</div>
						{/if}
						{#if typeof temperatureC === 'number'}
							<div class="flex justify-between">
								<span class="text-muted-foreground">Temperature</span>
								<span class="font-mono text-foreground">{temperatureC.toFixed(1)} &deg;C</span>
							</div>
						{/if}
					</div>
				</div>
			{/if}

			<!-- Dynamic: remaining properties + commands -->
			<DynamicProperties {deviceId} {devicesManager} exclusions={laserExclusions} />
		</div>
	{:else}
		<div class="flex items-center justify-center py-12">
			<p class="text-sm text-muted-foreground">Laser not available</p>
		</div>
	{/if}
</section>
