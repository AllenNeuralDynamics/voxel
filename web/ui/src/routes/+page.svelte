<script lang="ts">
	import { getAppContext } from '$lib/context';
	import { useSearchParams, createSearchParamsSchema } from 'runed/kit';
	import { cn, sanitizeString, wavelengthToColor } from '$lib/utils';
	import { Collapsible } from 'bits-ui';
	import { ChevronRight } from '$lib/icons';
	import { ProfileConfig } from '$lib/ui/profile';
	import { CameraConfig, LaserConfig, DaqConfig, DeviceConfig } from '$lib/ui/configure';

	type NavTarget = { type: 'device'; id: string } | { type: 'channels' } | { type: 'profile'; id: string };

	const app = getAppContext();
	const session = $derived(app.session!);
	const config = $derived(session.config);
	const daqDeviceId = $derived(config.daq.device);

	const params = useSearchParams(
		createSearchParamsSchema({
			nav: { type: 'string', default: 'channels' },
			id: { type: 'string', default: '' }
		}),
		{ pushHistory: false, noScroll: true }
	);

	const activeNav = $derived<NavTarget>(
		params.nav === 'device' && params.id
			? { type: 'device', id: params.id }
			: params.nav === 'profile' && params.id
				? { type: 'profile', id: params.id }
				: { type: 'channels' }
	);

	function setNav(nav: NavTarget) {
		if (nav.type === 'channels') {
			params.nav = 'channels';
			params.id = '';
		} else {
			params.nav = nav.type;
			params.id = nav.id;
		}
	}

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

	// --- Validate nav targets ---

	$effect(() => {
		if (activeNav.type === 'device') {
			const devices = session.devices.devices;
			if (!devices.has(activeNav.id)) {
				const firstId = [...devices.keys()][0];
				setNav(firstId ? { type: 'device', id: firstId } : { type: 'channels' });
			}
		} else if (activeNav.type === 'profile' && !(activeNav.id in session.config.profiles)) {
			setNav({ type: 'channels' });
		}
	});
</script>

<div class="flex h-full">
	<!-- Sidebar Navigation -->
	<aside class="flex w-56 shrink-0 flex-col gap-4 overflow-auto border-r border-border bg-card py-3">
		<!-- Channels -->
		<nav class="space-y-0.5 px-3">
			<button onclick={() => setNav({ type: 'channels' })} class={navClass({ type: 'channels' })}>
				Channels
			</button>
		</nav>

		<!-- Profiles -->
		<Collapsible.Root open>
			<Collapsible.Trigger class="group flex w-full items-center justify-between px-5 py-1">
				<span class="text-[0.5rem] font-medium tracking-wide text-muted-foreground uppercase"> Profiles </span>
				<ChevronRight
					width="12"
					height="12"
					class="shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90"
				/>
			</Collapsible.Trigger>
			<Collapsible.Content>
				<nav class="mt-1 space-y-0.5 px-3">
					{#each Object.entries(config.profiles) as [id, profile] (id)}
						{@const isActiveProfile = id === session.activeProfileId}
						{@const isViewed = activeNav.type === 'profile' && activeNav.id === id}
						<button
							onclick={() => setNav({ type: 'profile', id })}
							class="group {navClass({ type: 'profile', id })}"
						>
							<span class="truncate">{profile.label ?? sanitizeString(id)}</span>
							{#if isActiveProfile}
								<span
									class="w-13 shrink-0 rounded-full bg-success/15 py-0.5 text-center text-[0.5rem] font-medium text-success"
								>
									Active
								</span>
							{:else}
								<span
									role="button"
									tabindex="0"
									class={cn(
										'w-13 shrink-0 rounded-full border py-0.5 text-center text-[0.5rem] font-medium transition-all',
										isViewed
											? 'pointer-events-auto border-amber-500/40 bg-amber-500/10 text-amber-500 opacity-100 hover:bg-amber-500/20'
											: 'pointer-events-none border-border text-muted-foreground opacity-0 group-hover:pointer-events-auto group-hover:opacity-100 hover:bg-muted hover:text-foreground'
									)}
									onclick={(e: MouseEvent) => {
										e.stopPropagation();
										session.activateProfile(id);
										setNav({ type: 'profile', id });
									}}
									onkeydown={(e: KeyboardEvent) => {
										if (e.key === 'Enter') {
											e.stopPropagation();
											session.activateProfile(id);
											setNav({ type: 'profile', id });
										}
									}}
								>
									Activate
								</span>
							{/if}
						</button>
					{/each}
				</nav>
			</Collapsible.Content>
		</Collapsible.Root>

		<!-- Devices -->
		<Collapsible.Root open>
			<Collapsible.Trigger class="group flex w-full items-center justify-between px-5 py-1">
				<span class="text-[0.5rem] font-medium tracking-wide text-muted-foreground uppercase"> Devices </span>
				<ChevronRight
					width="12"
					height="12"
					class="shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90"
				/>
			</Collapsible.Trigger>
			<Collapsible.Content>
				<nav class="mt-1 space-y-0.5 px-3">
					{#each [...session.devices.devices] as [id, device] (id)}
						<button onclick={() => setNav({ type: 'device', id })} class={navClass({ type: 'device', id })}>
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
			</Collapsible.Content>
		</Collapsible.Root>
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
		{:else if activeNav.type === 'profile' && activeNav.id}
			<ProfileConfig {session} profileId={activeNav.id} />
		{:else if activeNav.type === 'device'}
			{#if activeNav.id in session.cameras}
				<CameraConfig {session} deviceId={activeNav.id} />
			{:else if activeNav.id in session.lasers}
				<LaserConfig {session} deviceId={activeNav.id} />
			{:else if activeNav.id === daqDeviceId}
				<DaqConfig {session} deviceId={activeNav.id} />
			{:else}
				<DeviceConfig {session} deviceId={activeNav.id} />
			{/if}
		{/if}
	</div>
</div>
