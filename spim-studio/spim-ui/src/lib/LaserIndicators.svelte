<script lang="ts">
	import { Tooltip } from 'bits-ui';
	import Icon from '@iconify/svelte';
	import type { RigManager } from '$lib/core';
	import { wavelengthToColor } from '$lib/utils';
	import Switch from '$lib/ui/Switch.svelte';
	import { SvelteMap } from 'svelte/reactivity';

	interface Props {
		rigManager: RigManager;
	}

	let { rigManager }: Props = $props();

	interface LaserInfo {
		deviceId: string;
		wavelength: number | undefined;
		isEnabled: boolean;
		powerMw: number | undefined;
		color: string;
	}

	// Derive laser information from channels config and device states
	const lasers = $derived.by(() => {
		const laserMap = new SvelteMap<string, LaserInfo>();

		// Extract unique laser device IDs from channel configs
		if (rigManager.config?.channels) {
			for (const channel of Object.values(rigManager.config.channels)) {
				if (channel.illumination) {
					const deviceId = channel.illumination;

					// Skip if we already have this laser
					if (laserMap.has(deviceId)) continue;

					const wavelength = rigManager.devices.getPropertyValue(deviceId, 'wavelength') as number | undefined;
					const isEnabled = (rigManager.devices.getPropertyValue(deviceId, 'is_enabled') as boolean) ?? false;
					const powerMw = rigManager.devices.getPropertyValue(deviceId, 'power_mw') as number | undefined;

					laserMap.set(deviceId, {
						deviceId,
						wavelength,
						isEnabled,
						powerMw,
						color: wavelengthToColor(wavelength)
					});
				}
			}
		}

		return Array.from(laserMap.values()).sort((a, b) => {
			// Sort by wavelength (ascending)
			const wlA = a.wavelength ?? Infinity;
			const wlB = b.wavelength ?? Infinity;
			return wlA - wlB;
		});
	});

	const anyLaserEnabled = $derived(lasers.some((l) => l.isEnabled));

	function handleToggleLaser(deviceId: string, currentState: boolean) {
		if (currentState) {
			rigManager.devices.executeCommand(deviceId, 'disable');
		} else {
			rigManager.devices.executeCommand(deviceId, 'enable');
		}
	}

	function handleEmergencyStop() {
		for (const laser of lasers) {
			if (laser.isEnabled) {
				rigManager.devices.executeCommand(laser.deviceId, 'disable');
			}
		}
	}
</script>

{#if lasers.length > 0}
	<Tooltip.Provider>
		<Tooltip.Root delayDuration={150}>
			<Tooltip.Trigger
				class="flex items-center gap-1 rounded-md px-2 py-1 transition-colors hover:bg-zinc-800/50 focus-visible:ring-2 focus-visible:ring-zinc-400 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-900 focus-visible:outline-none"
				aria-label="Laser controls"
			>
				{#each lasers as laser (laser.deviceId)}
					<div class="relative">
						{#if laser.isEnabled}
							<!-- Filled dot with pulsing animation when enabled -->
							<div
								class="h-2 w-2 rounded-full"
								style="background-color: {laser.color};"
								aria-label="{laser.wavelength}nm laser enabled"
							></div>
							<span
								class="absolute inset-0 animate-ping rounded-full opacity-75"
								style="background-color: {laser.color};"
							></span>
						{:else}
							<!-- Border-only dot when disabled -->
							<div
								class="h-2 w-2 rounded-full border opacity-70"
								style="border-color: {laser.color};"
								aria-label="{laser.wavelength}nm laser disabled"
							></div>
						{/if}
					</div>
				{/each}
			</Tooltip.Trigger>
			<Tooltip.Content
				class="z-50 w-72 rounded-md border border-zinc-700 bg-zinc-900 p-3 text-left text-xs text-zinc-200 shadow-xl outline-none"
				side="top"
				sideOffset={8}
			>
				<div class="space-y-3">
					<!-- Header -->
					<div class="flex items-center justify-between border-b border-zinc-800 pb-2">
						<span class="font-medium text-zinc-100">Laser Controls</span>
						{#if anyLaserEnabled}
							<button
								onclick={handleEmergencyStop}
								class="flex items-center gap-1.5 rounded bg-rose-600/20 px-2 py-1 text-xs text-rose-400 transition-colors hover:bg-rose-600/30 active:bg-rose-600/40"
								aria-label="Disable all lasers"
							>
								<Icon icon="mdi:power" width="14" height="14" />
								<span>Stop All</span>
							</button>
						{/if}
					</div>

					<!-- Individual laser controls -->
					<div class="space-y-2">
						{#each lasers as laser (laser.deviceId)}
							<div class="flex items-center justify-between gap-3 rounded-md bg-zinc-800/50 p-2">
								<div class="flex items-center gap-2">
									<!-- Color indicator -->
									<div class="h-2 w-2 rounded-full" style="background-color: {laser.color};"></div>

									<!-- Laser info -->
									<div class="flex items-center gap-2">
										<span class="font-medium text-zinc-100">
											{laser.wavelength ? `${laser.wavelength} nm` : 'Laser'}
										</span>
										{#if laser.isEnabled && laser.powerMw !== undefined}
											<span class="text-xs text-zinc-400">
												{laser.powerMw.toFixed(1)} mW
											</span>
										{/if}
									</div>
								</div>

								<!-- Toggle switch -->
								<Switch
									checked={laser.isEnabled}
									onCheckedChange={(checked) => handleToggleLaser(laser.deviceId, !checked)}
								/>
							</div>
						{/each}
					</div>
				</div>
			</Tooltip.Content>
		</Tooltip.Root>
	</Tooltip.Provider>
{/if}
