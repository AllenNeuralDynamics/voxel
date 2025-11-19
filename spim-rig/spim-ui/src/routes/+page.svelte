<script lang="ts">
	import { PreviewCanvas, Previewer, PreviewChannelControls, PreviewInfo } from '$lib/preview';
	import { onMount, onDestroy } from 'svelte';
	import { ProfilesManager } from '$lib/profiles.svelte';
	import ProfileSelector from '$lib/ProfileSelector.svelte';
	import { RigClient, ClientStatus } from '$lib/client';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/PaneDivider.svelte';
	import { DevicesManager } from '$lib/devices.svelte';
	import SliderInput from '$lib/ui/SliderInput.svelte';

	// Configuration
	import { browser } from '$app/environment';
	
	// Configuration
	const apiBaseUrl = browser ? window.location.origin : 'http://localhost:8000';
	const rigSocketUrl = browser 
		? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/rig`
		: 'ws://localhost:8000/ws/rig';

	// Component-level state
	let rigClient = $state<RigClient | undefined>(undefined);
	let previewer = $state<Previewer | undefined>(undefined);
	let profilesManager = $state<ProfilesManager | undefined>(undefined);
	let devicesManager = $state<DevicesManager | undefined>(undefined);

	onMount(async () => {
		try {
			// 1. Create and connect RigClient
			rigClient = new RigClient(rigSocketUrl);
			await rigClient.connect();
			console.log('[Page] RigClient connected');

			// 2. Initialize ProfilesManager
			profilesManager = new ProfilesManager({
				baseUrl: apiBaseUrl,
				rigClient
			});

			// 3. Initialize DevicesManager and fetch all data
			devicesManager = new DevicesManager({
				baseUrl: apiBaseUrl,
				rigClient
			});
			await devicesManager.initialize();
			console.log('[Page] DevicesManager initialized');

			// 4. Initialize Previewer
			previewer = new Previewer(rigClient);

			// 5. Request current rig status (will populate previewer channels)
			rigClient.requestRigStatus();

			console.log('[Page] All managers initialized');
		} catch (error) {
			console.error('[Page] Initialization failed:', error);
		}
	});

	onDestroy(() => {
		// Clean up in reverse order
		previewer?.shutdown();
		devicesManager?.destroy();
		profilesManager?.destroy();
		rigClient?.destroy();
		console.log('[Page] Cleanup complete');
	});

	function handleStartPreview() {
		previewer?.startPreview();
	}

	function handleStopPreview() {
		previewer?.stopPreview();
	}
</script>

<div class="flex h-screen w-full bg-zinc-950 text-zinc-100">
	{#if previewer && profilesManager && devicesManager}
		<aside class="flex h-full w-96 flex-col gap-4 border-r border-zinc-800 p-4">
			{#if previewer.channels.length === 0}
				<div class="flex flex-1 items-center justify-center">
					<p class="text-sm text-zinc-500">No channels available</p>
				</div>
			{:else}
				<div class="flex flex-1 flex-col gap-4 overflow-y-auto">
					{#each previewer.channels as channel (channel.idx)}
						{#if channel.name}
							<div class="space-y-4 rounded border border-zinc-700/80 bg-zinc-900/50 px-3 py-2">
								<!-- Preview Section -->
								<PreviewChannelControls {channel} {previewer} />

								<div class="space-y-2">
									<!-- Illumination Section -->
									{#if channel.config?.illumination && devicesManager}
										{@const laserDeviceId = channel.config.illumination}
										{@const laserDevice = devicesManager.getDevice(laserDeviceId)}
										{@const powerInfo = devicesManager.getPropertyInfo(laserDeviceId, 'power_setpoint_mw')}
										{@const powerModel = devicesManager.getPropertyModel(laserDeviceId, 'power_setpoint_mw')}

										{#if laserDevice?.connected && powerInfo && powerModel && typeof powerModel.value === 'number'}
											<SliderInput
												label={powerInfo.label}
												bind:value={powerModel.value}
												min={powerModel.min_val ?? 0}
												max={powerModel.max_val ?? 100}
												step={powerModel.step ?? 1}
												onchange={() => {
													if (typeof powerModel.value === 'number') {
														devicesManager?.setProperty(laserDeviceId, 'power_setpoint_mw', powerModel.value);
													}
												}}
											/>
										{:else}
											<div class="text-[0.6rem] text-zinc-500">Laser not available</div>
										{/if}
									{:else}
										<div class="text-[0.6rem] text-zinc-500">No laser configured</div>
									{/if}
									<!-- Detection Section (placeholder) -->
									<div class="h-16 py-1">
										<div class="text-[0.6rem] text-zinc-500">Exposure, gain, binning controls...</div>
									</div>
								</div>
							</div>
						{/if}
					{/each}
				</div>
			{/if}
		</aside>
		<main class="flex h-screen flex-1 flex-col overflow-hidden border-0 border-zinc-700">
			<PaneGroup direction="horizontal" autoSaveId="rootPanel">
				<Pane class="flex h-full flex-1 flex-col">
					<header class="flex items-start justify-between gap-4 p-4">
						<div class="flex gap-2">
							<button
								onclick={handleStartPreview}
								disabled={previewer.isPreviewing}
								class="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
							>
								Start
							</button>
							<button
								onclick={handleStopPreview}
								disabled={!previewer.isPreviewing}
								class="rounded bg-rose-600 px-3 py-1.5 text-sm font-medium transition-colors hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
							>
								Stop
							</button>
						</div>
						<ProfileSelector manager={profilesManager} />
					</header>
					<div class="flex-1 px-4">
						<PreviewCanvas {previewer} />
					</div>
				</Pane>
				<PaneDivider />
				<Pane defaultSize={20} maxSize={30}></Pane>
			</PaneGroup>
			<footer class="flex items-center justify-between border-t border-zinc-800 px-4 py-3">
				<PreviewInfo {previewer} />
				<ClientStatus client={rigClient} />
			</footer>
		</main>
	{:else}
		<div class="flex h-full w-full items-center justify-center">
			<p class="text-zinc-500">Loading...</p>
		</div>
	{/if}
</div>
