<script lang="ts">
	import type { Session } from '$lib/main';
	import { discoverProfileDevices, isFilterWheel, isPropDiverged, formatPropValue, decimalsFromStep } from '$lib/main';
	import { Collapsible } from 'bits-ui';
	import { ChevronRight, Restore } from '$lib/icons';
	import { Button, SpinBox, Select, Switch } from '$lib/ui/kit';
	import { sanitizeString, cn } from '$lib/utils';

	interface Props {
		session: Session;
		profileId?: string;
		class?: string;
	}

	let { session, profileId, class: className }: Props = $props();

	const effectiveProfileId = $derived(profileId ?? session.activeProfileId);
	const profile = $derived(effectiveProfileId ? session.config.profiles[effectiveProfileId] : undefined);
	const isActiveProfile = $derived(!!effectiveProfileId && effectiveProfileId === session.activeProfileId);

	/** Aux devices: everything except cameras, lasers, and filter wheels. */
	const devices = $derived.by(() => {
		if (!effectiveProfileId) return [];
		return discoverProfileDevices(session.config, effectiveProfileId).filter(
			(d) => d.role !== 'camera' && d.role !== 'laser' && !isFilterWheel(session.config, d.id)
		);
	});

	/** Per-device setup commands open state. */
	let setupOpen: Record<string, boolean> = $state({});
</script>

{#if !profile}
	<div class={cn('flex items-center justify-center py-12', className)}>
		<p class="text-sm text-fg-muted">No active profile</p>
	</div>
{:else if devices.length === 0}
	<div class={cn('flex items-center justify-center py-12', className)}>
		<p class="text-sm text-fg-muted">No auxiliary devices in profile</p>
	</div>
{:else}
	<div class={cn('grid grid-cols-[repeat(auto-fill,minmax(24rem,1fr))] items-start gap-3', className)}>
		{#each devices as { id: deviceId } (deviceId)}
			{@const device = session.devices.getDevice(deviceId)}
			{@const savedProps = profile.props?.[deviceId]}
			{@const setupCommands = profile.setup?.[deviceId]}

			{@const rwProperties = (() => {
				const props = device?.interface?.properties;
				if (!props) return [];
				return Object.entries(props)
					.filter(([, info]) => info.access === 'rw')
					.sort(([a], [b]) => a.localeCompare(b));
			})()}

			{@const hasContent = rwProperties.length > 0 || (savedProps != null && Object.keys(savedProps).length > 0)}

			{#if hasContent}
				<div class="rounded-lg border border-border p-3">
					<!-- Card header -->
					<div class="mb-2.5 flex items-center justify-between">
						<span class="text-sm font-medium text-fg">{sanitizeString(deviceId)}</span>
						{#if isActiveProfile}
							<div class="flex items-center gap-1">
								{#if session.devices.hasDivergence(deviceId, savedProps)}
									<Button
										variant="ghost"
										size="icon-xs"
										onclick={() => session.applyProfileProps([deviceId])}
										title="Revert to saved"
									>
										<Restore width="14" height="14" />
									</Button>
								{/if}
								<Button variant="outline" size="xs" onclick={() => session.saveProfileProps(deviceId)}>Save</Button>
							</div>
						{/if}
					</div>

					<!-- Properties -->
					<div class="space-y-1.5">
						{#each rwProperties as [propName, propInfo] (propName)}
							{@const saved = savedProps?.[propName]}
							{@const model = session.devices.getPropertyModel(deviceId, propName)}
							{@const current = model?.value}
							{@const propDiverged = isPropDiverged(saved, current)}
							{@const hasSaved = saved !== undefined && saved !== null}

							<div>
								<div class="flex items-center justify-between gap-3">
									<div class="flex items-center gap-1 text-xs text-fg-muted">
										<span class="min-w-0 shrink truncate" title={propInfo.desc || propInfo.label || propName}>
											{propInfo.label || propName}
										</span>
										{#if propInfo.units}
											<span class="opacity-50">({propInfo.units})</span>
										{/if}
										{#if propDiverged}
											<span class="text-warning opacity-90">({formatPropValue(saved, model?.step)})</span>
										{/if}
										{#if !hasSaved}
											<span class="inline-block size-1 rounded-full bg-warning opacity-70"></span>
										{/if}
									</div>

									<div class="w-40 shrink-0">
										{#if isActiveProfile && model}
											{#if model.options && model.options.length > 0}
												<Select
													size="xs"
													class="w-full"
													value={String(current ?? '')}
													options={model.options.map((o) => ({
														value: String(o),
														label: String(o)
													}))}
													onchange={(v) => {
														const numericOptions = model.options?.some((o) => typeof o === 'number');
														session.devices.setProperty(deviceId, propName, numericOptions ? Number(v) : v);
													}}
												/>
											{:else if propInfo.dtype.includes('bool') || typeof current === 'boolean'}
												<div class="flex justify-end">
													<Switch
														size="sm"
														checked={current === true}
														onCheckedChange={(v) => session.devices.setProperty(deviceId, propName, v)}
													/>
												</div>
											{:else if typeof current === 'number'}
												<SpinBox
													size="xs"
													appearance="full"
													class="w-full"
													value={current}
													min={model.min_val ?? -Infinity}
													max={model.max_val ?? Infinity}
													step={model.step ?? 1}
													decimals={decimalsFromStep(model.step)}
													numCharacters={6}
													onChange={(v) => session.devices.setProperty(deviceId, propName, v)}
												/>
											{:else}
												<span class="block text-right font-mono text-xs text-fg">
													{formatPropValue(current, model?.step)}
												</span>
											{/if}
										{:else}
											<span
												class="block text-right font-mono text-xs {current != null ? 'text-fg' : 'text-fg-muted/40'}"
											>
												{formatPropValue(current, model?.step)}
											</span>
										{/if}
									</div>
								</div>
							</div>
						{/each}
					</div>

					<!-- Setup commands -->
					{#if setupCommands && setupCommands.length > 0}
						<div class="mt-3 border-t border-border pt-2">
							<Collapsible.Root
								open={setupOpen[deviceId] ?? false}
								onOpenChange={(open) => {
									setupOpen = { ...setupOpen, [deviceId]: open };
								}}
							>
								<Collapsible.Trigger class="flex items-center gap-1 text-xs text-fg-muted hover:text-fg">
									<ChevronRight
										width="12"
										height="12"
										class="shrink-0 transition-transform {setupOpen[deviceId] ? 'rotate-90' : ''}"
									/>
									<span>Setup Commands ({setupCommands.length})</span>
								</Collapsible.Trigger>
								<Collapsible.Content class="mt-1 space-y-0.5 pl-4">
									{#each setupCommands as cmd, i (i)}
										<div class="font-mono text-xs text-fg-muted">
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
	</div>
{/if}
