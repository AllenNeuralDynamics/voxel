<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { App } from '$lib/main';
	import SplashScreen from '../SplashScreen.svelte';
	import LaunchScreen from '../LaunchScreen.svelte';
	import { PreviewCanvas } from '$lib/ui/preview';
	import { GridCanvas2 as GridCanvas } from '$lib/ui/grid/canvas';
	import LogViewer from '$lib/ui/LogViewer.svelte';
	import WaveformViewer from '$lib/ui/WaveformViewer.svelte';
	import ClientStatus from '$lib/ui/ClientStatus.svelte';
	import DeviceFilterToggle, { type DeviceFilter } from './DeviceFilterToggle.svelte';
	import ChannelSection from './ChannelSection.svelte';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/primitives/PaneDivider.svelte';
	import Icon from '@iconify/svelte';
	import { sanitizeString, wavelengthToColor } from '$lib/utils';
	import ProfileSelector from '$lib/ui/ProfileSelector.svelte';
	import Switch from '$lib/ui/primitives/Switch.svelte';
	import { SvelteMap } from 'svelte/reactivity';

	let app = $state<App | undefined>(undefined);

	// Control view state
	let deviceFilter = $state<DeviceFilter>('all');
	let bottomPanelTab = $state('session');
	let bottomPane: Pane | undefined = $state(undefined);

	function selectBottomTab(tab: string) {
		if (bottomPanelTab === tab) {
			if (bottomPane?.isCollapsed()) bottomPane.expand();
			else bottomPane?.collapse();
		} else {
			bottomPanelTab = tab;
			if (bottomPane?.isCollapsed()) bottomPane.expand();
		}
	}

	// Workflow modes
	type WorkflowMode = 'scout' | 'plan' | 'acquire';
	let workflowMode = $state<WorkflowMode>('scout');
	let completedModes = $state(new Set<WorkflowMode>());

	// Laser state (derived from active session)
	interface LaserInfo {
		deviceId: string;
		wavelength: number | undefined;
		isEnabled: boolean;
		powerMw: number | undefined;
		color: string;
	}

	const lasers = $derived.by(() => {
		if (!app?.session?.config?.channels) return [] as LaserInfo[];
		const session = app.session;
		const laserMap = new SvelteMap<string, LaserInfo>();
		for (const channel of Object.values(session.config.channels)) {
			if (!channel.illumination || laserMap.has(channel.illumination)) continue;
			const deviceId = channel.illumination;
			laserMap.set(deviceId, {
				deviceId,
				wavelength: session.devices.getPropertyValue(deviceId, 'wavelength') as number | undefined,
				isEnabled: (session.devices.getPropertyValue(deviceId, 'is_enabled') as boolean) ?? false,
				powerMw: session.devices.getPropertyValue(deviceId, 'power_mw') as number | undefined,
				color: wavelengthToColor(session.devices.getPropertyValue(deviceId, 'wavelength') as number | undefined)
			});
		}
		return Array.from(laserMap.values()).sort((a, b) => (a.wavelength ?? Infinity) - (b.wavelength ?? Infinity));
	});

	const anyLaserEnabled = $derived(lasers.some((l) => l.isEnabled));

	function toggleLaser(deviceId: string, currentState: boolean) {
		app?.session?.devices.executeCommand(deviceId, currentState ? 'disable' : 'enable');
	}

	function stopAllLasers() {
		for (const laser of lasers) {
			if (laser.isEnabled) app?.session?.devices.executeCommand(laser.deviceId, 'disable');
		}
	}

	function cleanup() {
		if (app) {
			app.destroy();
			app = undefined;
		}
	}

	onMount(async () => {
		window.addEventListener('beforeunload', cleanup);
		try {
			app = new App();
			await app.initialize();
		} catch {
			// Connection state managed by client — splash handles the UI
		}
	});

	onDestroy(() => {
		window.removeEventListener('beforeunload', cleanup);
		cleanup();
	});
</script>

{#if app?.session}
	{@const session = app.session}
	{@const activeProfileLabel = (() => {
		const p = session.activeProfile;
		return p ? (p.label ?? p.desc ?? sanitizeString(p.id)) : 'No profile';
	})()}
	<div class="flex h-screen w-full bg-background text-foreground">
		<!-- Left panel: Channels & Imaging -->
		<aside class="flex h-full w-96 min-w-80 flex-col border-r border-border bg-card">
			<div class="space-y-3 border-b border-border p-4">
				<ProfileSelector {session} />
				<DeviceFilterToggle bind:value={deviceFilter} onValueChange={(v) => (deviceFilter = v)} />
			</div>

			{#if session.previewState.channels.length === 0}
				<div class="flex flex-1 items-center justify-center p-4">
					<p class="text-sm text-muted-foreground">No channels available</p>
				</div>
			{:else}
				<div class="flex flex-1 flex-col overflow-y-auto">
					{#each session.previewState.channels as channel (channel.idx)}
						{#if channel.name}
							<div>
								<ChannelSection {channel} devices={session.devices} {deviceFilter} />
							</div>
							<div class="border-t border-border"></div>
						{/if}
					{/each}
				</div>
			{/if}

			<footer class="mt-auto flex p-4">
				<ClientStatus client={app.client} />
			</footer>
		</aside>

		<!-- Middle column: Acquisition planning -->
		<div class="flex h-full flex-1 flex-col border-r border-border">
			<header class="flex items-center gap-3 border-b border-border bg-card px-4 py-4">
				{#each [{ id: 'scout', label: 'Scout' }, { id: 'plan', label: 'Plan' }, { id: 'acquire', label: 'Acquire' }] as mode, i (mode.id)}
					{@const isActive = workflowMode === mode.id}
					{@const isComplete = completedModes.has(mode.id as WorkflowMode)}
					{#if i > 0}
						<div class="h-px w-4 bg-border"></div>
					{/if}
					<button
						onclick={() => (workflowMode = mode.id as WorkflowMode)}
						class="flex items-center gap-2 text-xs transition-colors {isActive
							? 'text-foreground'
							: 'text-muted-foreground hover:text-foreground'}"
					>
						<div
							class="flex h-3.5 w-3.5 items-center justify-center rounded-full border transition-colors {isComplete
								? 'border-success bg-success text-white'
								: isActive
									? 'border-foreground'
									: 'border-muted-foreground/50'}"
						>
							{#if isComplete}
								<Icon icon="mdi:check" width="8" height="8" />
							{/if}
						</div>
						<span class:font-medium={isActive}>{mode.label}</span>
					</button>
				{/each}
			</header>
			<PaneGroup direction="vertical" autoSaveId="midCol-v3">
				<Pane minSize={30}>
					<div class="h-full overflow-auto p-4">
						{#if workflowMode === 'scout'}
							<div class="flex h-full items-center justify-center">
								<p class="text-sm text-muted-foreground">Scout — explore sample and capture snapshots</p>
							</div>
						{:else if workflowMode === 'plan'}
							<div class="flex h-full items-center justify-center">
								<p class="text-sm text-muted-foreground">Plan — configure grid and define stacks</p>
							</div>
						{:else if workflowMode === 'acquire'}
							<div class="flex h-full items-center justify-center">
								<p class="text-sm text-muted-foreground">Acquire — run acquisition and monitor progress</p>
							</div>
						{/if}
					</div>
				</Pane>
				<PaneDivider direction="horizontal" class="text-border hover:text-muted-foreground" />
				<Pane
					bind:this={bottomPane}
					collapsible
					collapsedSize={0}
					defaultSize={0}
					minSize={15}
					maxSize={50}
					onCollapse={() => {}}
				>
					{#if bottomPanelTab === 'session'}
						<div class="h-full overflow-auto bg-card p-4">
							<div class="space-y-4 text-sm text-muted-foreground">
								<h3 class="text-xs font-medium uppercase">Session Info</h3>
								<div class="grid grid-cols-2 gap-2 text-xs">
									<span>Config</span>
									<span class="text-foreground">{session.config.info.name}</span>
									<span>Active profile</span>
									<span class="text-foreground">{activeProfileLabel}</span>
									<span>Tiles</span>
									<span class="text-foreground">{session.tiles.length}</span>
									<span>Stacks</span>
									<span class="text-foreground">{session.stacks.length}</span>
									<span>Stage connected</span>
									<span class="text-foreground">{session.stageConnected ? 'Yes' : 'No'}</span>
								</div>

								<h3 class="text-xs font-medium uppercase">Stage</h3>
								<div class="grid grid-cols-2 gap-2 text-xs">
									<span>X position</span>
									<span class="text-foreground">{session.xAxis.position.toFixed(3)} mm</span>
									<span>Y position</span>
									<span class="text-foreground">{session.yAxis.position.toFixed(3)} mm</span>
									<span>Z position</span>
									<span class="text-foreground">{session.zAxis.position.toFixed(3)} mm</span>
									<span>Moving</span>
									<span class="text-foreground">{session.stageIsMoving ? 'Yes' : 'No'}</span>
								</div>

								<h3 class="text-xs font-medium uppercase">Grid</h3>
								<div class="grid grid-cols-2 gap-2 text-xs">
									<span>Overlap</span>
									<span class="text-foreground">{(session.gridConfig.overlap * 100).toFixed(0)}%</span>
									<span>Tile order</span>
									<span class="text-foreground">{session.tileOrder}</span>
									<span>Grid locked</span>
									<span class="text-foreground">{session.gridLocked ? 'Yes' : 'No'}</span>
									<span>FOV</span>
									<span class="text-foreground"
										>{session.fov.width.toFixed(2)} x {session.fov.height.toFixed(2)} mm</span
									>
								</div>
							</div>
						</div>
					{:else if bottomPanelTab === 'waveforms'}
						<div class="h-full overflow-hidden bg-card">
							<WaveformViewer {session} />
						</div>
					{:else if bottomPanelTab === 'lasers'}
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
										<Icon icon="mdi:power" width="14" height="14" />
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
										<Switch
											checked={laser.isEnabled}
											onCheckedChange={(checked) => toggleLaser(laser.deviceId, !checked)}
										/>
									</div>
								{/each}
								{#if lasers.length === 0}
									<p class="text-xs text-muted-foreground">No lasers configured</p>
								{/if}
							</div>
						</div>
					{:else if bottomPanelTab === 'logs'}
						<div class="h-full overflow-hidden bg-card p-2">
							<LogViewer logs={app.logs} onClear={() => app?.clearLogs()} />
						</div>
					{/if}
				</Pane>
			</PaneGroup>

			<footer class="flex items-center justify-between border-t border-border bg-card px-4 py-2">
				<div class="flex rounded border border-border">
					{#each [{ id: 'session', label: 'Session' }, { id: 'waveforms', label: 'Waveforms' }, { id: 'logs', label: 'Logs' }] as tab, i (tab.id)}
						<button
							onclick={() => selectBottomTab(tab.id)}
							class="px-2 py-0.5 text-xs transition-colors hover:bg-accent {bottomPanelTab === tab.id
								? 'bg-accent text-foreground'
								: 'text-muted-foreground'} {i > 0 ? 'border-l border-border' : ''}"
						>
							{tab.label}
						</button>
					{/each}
					<button
						onclick={() => selectBottomTab('lasers')}
						class="flex items-center gap-1 border-l border-border px-2 py-0.5 text-xs transition-colors hover:bg-accent {bottomPanelTab ===
						'lasers'
							? 'bg-accent text-foreground'
							: 'text-muted-foreground'}"
					>
						{#if lasers.length > 0}
							{#each lasers as laser (laser.deviceId)}
								<div class="relative">
									{#if laser.isEnabled}
										<div class="h-1.5 w-1.5 rounded-full" style="background-color: {laser.color};"></div>
										<span
											class="absolute inset-0 animate-ping rounded-full opacity-75"
											style="background-color: {laser.color};"
										></span>
									{:else}
										<div class="h-1.5 w-1.5 rounded-full border opacity-70" style="border-color: {laser.color};"></div>
									{/if}
								</div>
							{/each}
						{:else}
							<Icon icon="mdi:laser-pointer" width="12" height="12" />
						{/if}
					</button>
				</div>

				<button
					onclick={() => app?.closeSession()}
					class="flex cursor-pointer items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
					aria-label="Close Session"
					title="Close Session"
				>
					<Icon icon="mdi:exit-to-app" width="20" height="20" />
				</button>
			</footer>
		</div>

		<!-- Right column: Preview + Grid Canvas -->
		<main class="flex h-full flex-1 flex-col overflow-hidden">
			<PaneGroup direction="vertical" autoSaveId="rightCol-v3">
				<Pane defaultSize={50} minSize={30} class="flex flex-1 flex-col justify-center px-4">
					<GridCanvas {session} />
				</Pane>
				<PaneDivider direction="horizontal" class="text-border hover:text-muted-foreground" />
				<Pane defaultSize={50} minSize={30} class="h-full flex-1 px-4">
					<PreviewCanvas previewer={session.previewState} />
				</Pane>
			</PaneGroup>
		</main>
	</div>
{:else if app?.status?.phase === 'idle'}
	<LaunchScreen {app} />
{:else}
	<SplashScreen {app} />
{/if}
