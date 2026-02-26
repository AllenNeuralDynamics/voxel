<script lang="ts">
	import type { Session } from '$lib/main';
	import Switch from '$lib/ui/kit/Switch.svelte';
	import { Power } from '$lib/icons';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	const lasers = $derived(Object.values(session.lasers));
	const anyLaserEnabled = $derived(lasers.some((l) => l.isEnabled));

	function stopAllLasers() {
		for (const laser of lasers) {
			if (laser.isEnabled) laser.disable();
		}
	}
</script>

<div class="h-full overflow-auto bg-card p-4">
	<div class="space-y-3">
		<div class="flex items-center justify-between">
			<h3 class="text-xs font-medium text-muted-foreground uppercase">Laser Controls</h3>
			<button
				onclick={stopAllLasers}
				class="flex items-center gap-1.5 rounded bg-danger/20 px-2 py-1 text-xs text-danger transition-all hover:bg-danger/30 {anyLaserEnabled
					? ''
					: 'pointer-events-none opacity-0'}"
			>
				<Power width="14" height="14" />
				<span>Stop All</span>
			</button>
		</div>
		{#each lasers as laser (laser.deviceId)}
			<div class="flex items-center justify-between gap-3 rounded-md bg-muted/50 p-2">
				<div class="flex items-center gap-2">
					<div class="h-2 w-2 rounded-full" style="background-color: {laser.color};"></div>
					<span class="text-xs font-medium">{laser.wavelength ? `${laser.wavelength} nm` : 'Laser'}</span>
					{#if laser.isEnabled && laser.powerMw !== undefined}
						<span class="text-xs text-muted-foreground">{laser.powerMw.toFixed(1)} mW</span>
					{/if}
				</div>
				<Switch checked={laser.isEnabled} onCheckedChange={() => laser.toggle()} />
			</div>
		{/each}
		{#if Object.keys(session.lasers).length === 0}
			<p class="text-xs text-muted-foreground">No lasers configured</p>
		{/if}
	</div>
</div>
