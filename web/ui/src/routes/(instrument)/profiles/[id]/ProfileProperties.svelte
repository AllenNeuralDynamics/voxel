<script lang="ts">
	import type { Session } from '$lib/main';
	import { discoverProfileDevices, isFilterWheel } from '$lib/main';
	import { Collapsible } from 'bits-ui';
	import { ChevronRight } from '$lib/icons';
	import { Button } from '$lib/ui/kit';
	import { sanitizeString } from '$lib/utils';

	function isPropDiverged(saved: unknown, current: unknown): boolean {
		if (saved === undefined || saved === null) return false;
		if (current === undefined || current === null) return false;
		if (typeof saved === 'number' && typeof current === 'number') {
			return Math.abs(saved - current) > 1e-6;
		}
		return saved !== current;
	}

	function hasDeviceDivergence(s: Session, pid: string, deviceId: string): boolean {
		const savedProps = s.config.profiles[pid]?.props?.[deviceId];
		if (!savedProps) return false;
		for (const [propName, savedValue] of Object.entries(savedProps)) {
			const currentValue = s.devices.getPropertyModel(deviceId, propName)?.value;
			if (isPropDiverged(savedValue, currentValue)) return true;
		}
		return false;
	}

	function formatPropValue(value: unknown, step?: number | null): string {
		if (value === undefined || value === null) return '\u2014';
		if (typeof value === 'boolean') return value ? 'true' : 'false';
		if (typeof value === 'number') {
			if (step != null && step > 0) {
				const decimals = Math.max(0, -Math.floor(Math.log10(step)));
				return value.toFixed(decimals);
			}
			return Number.isInteger(value) ? value.toString() : value.toFixed(4);
		}
		return String(value);
	}

	function countDivergedProps(s: Session, pid: string): number {
		const p = s.config.profiles[pid];
		if (!p?.props) return 0;
		let count = 0;
		for (const [deviceId, savedProps] of Object.entries(p.props)) {
			for (const [propName, savedValue] of Object.entries(savedProps)) {
				const currentValue = s.devices.getPropertyModel(deviceId, propName)?.value;
				if (isPropDiverged(savedValue, currentValue)) count++;
			}
		}
		return count;
	}

	interface Props {
		session: Session;
		profileId: string;
	}

	let { session, profileId }: Props = $props();

	const profile = $derived(session.config.profiles[profileId]);

	/** All profile devices excluding filter wheels, sorted by role. */
	const devices = $derived(
		discoverProfileDevices(session.config, profileId).filter((d) => !isFilterWheel(session.config, d.id))
	);

	const isActiveProfile = $derived(profileId === session.activeProfileId);
	const divergedCount = $derived(isActiveProfile ? countDivergedProps(session, profileId) : 0);

	/** Per-device setup commands open state. */
	let setupOpen: Record<string, boolean> = $state({});
</script>

{#if profile}
	<div class="space-y-4">
		<!-- Device sections -->
		{#each devices as { id: deviceId } (deviceId)}
			{@const device = session.devices.getDevice(deviceId)}
			{@const savedProps = profile.props?.[deviceId]}
			{@const setupCommands = profile.setup?.[deviceId]}
			{@const diverged = hasDeviceDivergence(session, profileId, deviceId)}

			{@const rwProperties = (() => {
				const props = device?.interface?.properties;
				if (!props) return [];
				return Object.entries(props)
					.filter(([, info]) => info.access === 'rw')
					.sort(([a], [b]) => a.localeCompare(b));
			})()}

			{@const hasContent = rwProperties.length > 0 || (savedProps != null && Object.keys(savedProps).length > 0)}

			{#if hasContent}
				<div>
					<!-- Device header -->
					<div class="mb-1.5 flex items-center gap-2 text-sm">
						<span class="text-fg font-medium">{sanitizeString(deviceId)}</span>
						{#if diverged}
							<span class="h-1.5 w-1.5 rounded-full bg-warning" title="Properties diverged"></span>
						{/if}
					</div>

					<!-- Property table -->
					<div class="text-xs">
						<div class="text-fg-muted grid grid-cols-[1fr_auto_auto] gap-x-4 border-b pb-1">
							<span>Property</span>
							<span class="w-24 text-right">Saved</span>
							<span class="w-24 text-right">Current</span>
						</div>

						{#each rwProperties as [propName, propInfo] (propName)}
							{@const saved = savedProps?.[propName]}
							{@const model = session.devices.getPropertyModel(deviceId, propName)}
							{@const current = model?.value}
							{@const propDiverged = isPropDiverged(saved, current)}
							<div class="grid grid-cols-[1fr_auto_auto] items-center gap-x-4 py-0.5">
								<span class="text-fg-muted truncate" title={propInfo.label || propName}>
									{propInfo.label || propName}
									{#if propInfo.units}
										<span class="text-fg-muted/50">({propInfo.units})</span>
									{/if}
								</span>
								<span class="w-24 text-right font-mono {saved != null ? 'text-fg' : 'text-fg-muted/40'}">
									{formatPropValue(saved, model?.step)}
								</span>
								<span class="flex w-24 items-center justify-end gap-1 font-mono">
									{#if propDiverged}
										<span class="h-1.5 w-1.5 shrink-0 rounded-full bg-warning" title="Diverged from saved"></span>
									{/if}
									<span class={current != null ? 'text-fg' : 'text-fg-muted/40'}>
										{formatPropValue(current, model?.step)}
									</span>
								</span>
							</div>
						{/each}
					</div>

					<!-- Setup commands -->
					{#if setupCommands && setupCommands.length > 0}
						<div class="mt-2">
							<Collapsible.Root
								open={setupOpen[deviceId] ?? false}
								onOpenChange={(open) => {
									setupOpen = { ...setupOpen, [deviceId]: open };
								}}
							>
								<Collapsible.Trigger class="text-fg-muted hover:text-fg flex items-center gap-1 text-xs">
									<ChevronRight
										width="12"
										height="12"
										class="shrink-0 transition-transform {setupOpen[deviceId] ? 'rotate-90' : ''}"
									/>
									<span>Setup Commands ({setupCommands.length})</span>
								</Collapsible.Trigger>
								<Collapsible.Content class="mt-1 space-y-0.5 pl-4">
									{#each setupCommands as cmd, i (i)}
										<div class="text-fg-muted font-mono text-xs">
											<span class="text-fg">{cmd.attr}</span>
											{#if cmd.kwargs && Object.keys(cmd.kwargs).length > 0}
												<span class="text-fg-muted/60">
													({Object.entries(cmd.kwargs)
														.map(([k, v]) => `${k}=${JSON.stringify(v)}`)
														.join(', ')})
												</span>
											{/if}
										</div>
									{/each}
								</Collapsible.Content>
							</Collapsible.Root>
						</div>
					{/if}
				</div>
			{/if}
		{/each}

		<!-- Footer: divergence summary + actions -->
		{#if isActiveProfile}
			<div class="flex items-center justify-between border-t pt-3 text-xs">
				<span class="text-fg-muted">
					{#if divergedCount > 0}
						{divergedCount} {divergedCount === 1 ? 'property' : 'properties'} diverged
					{:else}
						All properties match saved values
					{/if}
				</span>
				<div class="flex gap-1.5">
					<Button variant="outline" size="sm" onclick={() => session.applyProfileProps()}>Reset</Button>
					<Button variant="outline" size="sm" onclick={() => session.saveAllProfileProps()}>Save All</Button>
				</div>
			</div>
		{/if}
	</div>
{/if}
