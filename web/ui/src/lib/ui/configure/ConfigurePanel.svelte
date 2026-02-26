<script lang="ts">
	import type { Session } from '$lib/main';
	import { cn, sanitizeString, wavelengthToColor } from '$lib/utils';
	import { Collapsible } from 'bits-ui';
	import { ChevronRight } from '$lib/icons';
	import ProfileConfig from './ProfileConfig.svelte';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	const config = $derived(session.config);
	const daqDeviceId = $derived(config.daq.device);

	type NavTarget = { type: 'device'; id: string } | { type: 'channels' } | { type: 'profile'; id: string };

	let activeNav = $state<NavTarget>({ type: 'channels' });

	function isActive(target: NavTarget): boolean {
		if (activeNav.type !== target.type) return false;
		if (target.type === 'device' && activeNav.type === 'device') return activeNav.id === target.id;
		if (target.type === 'profile' && activeNav.type === 'profile') return activeNav.id === target.id;
		return true;
	}

	function navClass(target: NavTarget): string {
		return cn(
			'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-xs cursor-pointer transition-colors',
			isActive(target)
				? 'bg-accent text-accent-foreground'
				: 'text-muted-foreground hover:bg-muted hover:text-foreground'
		);
	}
</script>

<div class="flex h-full">
	<!-- Sidebar Navigation -->
	<aside class="flex w-52 shrink-0 flex-col overflow-auto border-r border-border bg-card p-3">
		<!-- Channels -->
		<nav class="space-y-0.5">
			<button onclick={() => (activeNav = { type: 'channels' })} class={navClass({ type: 'channels' })}>
				Channels
			</button>
		</nav>

		<div class="my-3 border-t border-border"></div>

		<!-- Profiles -->
		<Collapsible.Root open>
			<Collapsible.Trigger class="group flex w-full items-center justify-between px-2 py-1">
				<span class="text-[0.65rem] font-medium tracking-wide text-muted-foreground uppercase"> Profiles </span>
				<ChevronRight
					width="12"
					height="12"
					class="shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90"
				/>
			</Collapsible.Trigger>
			<Collapsible.Content>
				<nav class="mt-1 space-y-0.5">
					{#each Object.entries(config.profiles) as [id, profile] (id)}
						<button onclick={() => (activeNav = { type: 'profile', id })} class={navClass({ type: 'profile', id })}>
							<span class="truncate">{profile.label ?? sanitizeString(id)}</span>
						</button>
					{/each}
				</nav>
			</Collapsible.Content>
		</Collapsible.Root>

		<div class="my-3 border-t border-border"></div>

		<!-- Devices -->
		<div>
			<h3 class="mb-1 px-2 text-[0.65rem] font-medium tracking-wide text-muted-foreground uppercase">Devices</h3>
			<nav class="space-y-0.5">
				{#each [...session.devices.devices] as [id, device] (id)}
					<button onclick={() => (activeNav = { type: 'device', id })} class={navClass({ type: 'device', id })}>
						<span class="truncate">{sanitizeString(id)}</span>
						<span
							class={cn(
								'h-1.5 w-1.5 shrink-0 rounded-full',
								device.connected ? 'bg-success' : 'bg-muted-foreground/30'
							)}
							title={device.connected ? 'Connected' : 'Disconnected'}
						></span>
					</button>
				{/each}
			</nav>
		</div>
	</aside>

	<!-- Main Content -->
	<div class="flex-1 overflow-auto p-6">
		{#if activeNav.type === 'channels'}
			<!-- Channel cards -->
			<section>
				<h3 class="mb-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">Channels</h3>
				<div class="grid auto-rows-auto grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3">
					{#each Object.entries(config.channels) as [channelId, channel] (channelId)}
						<div class="rounded-lg border bg-card p-3 text-xs text-card-foreground shadow-sm">
							<div class="mb-2 flex items-center gap-2">
								{#if channel.emission}
									<span
										class="h-2.5 w-2.5 shrink-0 rounded-full"
										style="background-color: {wavelengthToColor(channel.emission)}"
									></span>
								{/if}
								<span class="font-medium text-foreground">
									{channel.label ?? sanitizeString(channelId)}
								</span>
							</div>
							<div class="space-y-1 text-muted-foreground">
								<div class="flex justify-between">
									<span>Detection</span>
									<span class="text-foreground">{channel.detection}</span>
								</div>
								<div class="flex justify-between">
									<span>Illumination</span>
									<span class="text-foreground">{channel.illumination}</span>
								</div>
								{#each Object.entries(channel.filters) as [fwId, position] (fwId)}
									<div class="flex justify-between">
										<span>{fwId}</span>
										<span class="text-foreground">{position}</span>
									</div>
								{/each}
							</div>
						</div>
					{/each}
				</div>
			</section>
		{:else if activeNav.type === 'profile'}
			<ProfileConfig {session} profileId={activeNav.id} />
		{:else if activeNav.type === 'device'}
			{#if activeNav.id === daqDeviceId}
				<section>
					<h3 class="mb-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">Acquisition Ports</h3>
					<div class="space-y-1">
						{#each Object.entries(config.daq.acq_ports) as [deviceId, port] (deviceId)}
							<div class="flex items-center justify-between rounded px-2 py-1.5 text-xs">
								<span class="text-foreground">{deviceId}</span>
								<span class="font-mono text-muted-foreground">{port}</span>
							</div>
						{/each}
					</div>
				</section>
			{:else}
				<div class="flex items-center justify-center py-12">
					<p class="text-sm text-muted-foreground">
						{sanitizeString(activeNav.id)} — device details coming soon
					</p>
				</div>
			{/if}
		{/if}
	</div>
</div>
