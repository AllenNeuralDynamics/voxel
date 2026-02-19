<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { App } from '$lib/main';
	import SplashScreen from '../SplashScreen.svelte';
	import LaunchScreen from '../LaunchScreen.svelte';
	import { PreviewCanvas } from '$lib/ui/preview';
	import LogViewer from '$lib/ui/LogViewer.svelte';
	import ClientStatus from '$lib/ui/ClientStatus.svelte';
	import DeviceFilterToggle, { type DeviceFilter } from './DeviceFilterToggle.svelte';
	import ChannelSection from './ChannelSection.svelte';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/primitives/PaneDivider.svelte';
	import { Tabs } from 'bits-ui';
	import Icon from '@iconify/svelte';
	import { sanitizeString } from '$lib/utils';
	import ProfileSelector from '$lib/ui/ProfileSelector.svelte';

	let app = $state<App | undefined>(undefined);

	// Control view state
	let deviceFilter = $state<DeviceFilter>('all');
	let bottomPanelTab = $state('logs');

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
		<!-- Main content -->
		<main class="flex h-screen flex-1 flex-col overflow-hidden">
			<Tabs.Root bind:value={bottomPanelTab} class="flex h-full flex-col">
				<PaneGroup direction="vertical" autoSaveId="centerPanel-v3">
					<!-- Preview -->
					<Pane defaultSize={60} minSize={30} class="h-full flex-1 px-4">
						<PreviewCanvas previewer={session.previewState} />
					</Pane>
					<PaneDivider direction="horizontal" class="text-border hover:text-muted-foreground" />

					<!-- Bottom panel -->
					<Pane defaultSize={40} maxSize={70} minSize={20} class="overflow-hidden">
						<Tabs.Content value="logs" class="h-full overflow-hidden bg-card p-2">
							<LogViewer logs={app.logs} onClear={() => app?.clearLogs()} />
						</Tabs.Content>

						<Tabs.Content value="session" class="h-full overflow-auto bg-card p-4">
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
									<span class="text-foreground">{session.fov.width.toFixed(2)} x {session.fov.height.toFixed(2)} mm</span>
								</div>
							</div>
						</Tabs.Content>
					</Pane>
				</PaneGroup>

				<footer class="relative flex items-center justify-between border-t border-border px-4 py-3">
					<div class="flex items-center gap-3">
						<Tabs.List class="flex rounded border border-border">
							<Tabs.Trigger
								value="logs"
								class="px-2 py-0.5 text-xs transition-colors hover:bg-accent data-[state=active]:bg-accent data-[state=active]:text-foreground data-[state=inactive]:text-muted-foreground"
							>
								Logs
							</Tabs.Trigger>
							<Tabs.Trigger
								value="session"
								class="border-l border-border px-2 py-0.5 text-xs transition-colors hover:bg-accent data-[state=active]:bg-accent data-[state=active]:text-foreground data-[state=inactive]:text-muted-foreground"
							>
								Session
							</Tabs.Trigger>
						</Tabs.List>
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
			</Tabs.Root>
		</main>

		<!-- Right panel -->
		<aside class="flex h-full w-96 min-w-80 flex-col border-l border-border bg-card">
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
								<ChannelSection
									{channel}
									devices={session.devices}
									{deviceFilter}
								/>
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
	</div>
{:else if app?.status?.phase === 'idle'}
	<LaunchScreen {app} />
{:else}
	<SplashScreen {app} />
{/if}
