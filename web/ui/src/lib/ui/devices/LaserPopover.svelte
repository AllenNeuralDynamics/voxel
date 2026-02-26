<script lang="ts">
	import { Tooltip } from 'bits-ui';
	import { Power } from '$lib/icons';
	import type { Session } from '$lib/main';
	import Switch from '$lib/ui/primitives/Switch.svelte';
	import LaserIndicators from './LaserIndicators.svelte';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	const lasers = $derived(Object.values(session.lasers));
	const anyLaserEnabled = $derived(lasers.some((l) => l.isEnabled));

	function handleEmergencyStop() {
		for (const laser of lasers) {
			if (laser.isEnabled) laser.disable();
		}
	}
</script>

{#if Object.keys(session.lasers).length > 0}
	<Tooltip.Provider>
		<Tooltip.Root delayDuration={150}>
			<Tooltip.Trigger
				class="flex items-center gap-1 rounded-md px-2 py-1 transition-colors hover:bg-zinc-800/50 focus-visible:ring-2 focus-visible:ring-zinc-400 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-900 focus-visible:outline-none"
				aria-label="Laser controls"
			>
				<LaserIndicators lasers={session.lasers} size="md" />
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
								<Power width="14" height="14" />
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
									onCheckedChange={() => laser.toggle()}
								/>
							</div>
						{/each}
					</div>
				</div>
			</Tooltip.Content>
		</Tooltip.Root>
	</Tooltip.Provider>
{/if}
