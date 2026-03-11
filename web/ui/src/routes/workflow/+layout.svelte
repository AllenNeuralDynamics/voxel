<script lang="ts">
	import { getAppContext } from '$lib/context';
	import { cn } from '$lib/utils';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import LogViewer from '$lib/ui/LogViewer.svelte';
	import LasersPanel from '../LasersPanel.svelte';
	import CamerasPanel from '../CamerasPanel.svelte';
	import { ProfileSelector } from '$lib/ui/profile';

	let { children } = $props();

	const app = getAppContext();
	const session = $derived(app.session!);

	let bottomPanelTab = $state('lasers');
	let bottomPane: Pane | undefined = $state(undefined);

	function selectTab(id: string) {
		if (bottomPanelTab === id) {
			if (bottomPane?.isCollapsed()) bottomPane.expand();
			else bottomPane?.collapse();
		} else {
			bottomPanelTab = id;
			if (bottomPane?.isCollapsed()) bottomPane.expand();
		}
	}

	function tabClass(selected: boolean): string {
		return cn(
			'gap-2 flex items-center px-2 py-0.5 text-xs transition-colors hover:bg-muted',
			selected ? 'bg-muted text-foreground' : 'text-muted-foreground'
		);
	}
</script>

<PaneGroup direction="vertical" autoSaveId="workflow-v">
	<Pane>
		<div class="h-full overflow-auto">
			{@render children()}
		</div>
	</Pane>
	<PaneDivider
		direction="horizontal"
		ondblclick={() => {
			if (bottomPane?.isCollapsed()) bottomPane.expand();
			else bottomPane?.collapse();
		}}
	/>
	<Pane
		bind:this={bottomPane}
		collapsible
		collapsedSize={0}
		defaultSize={30}
		minSize={30}
		maxSize={50}
		onCollapse={() => {}}
	>
		{#if bottomPanelTab === 'cameras'}
			<CamerasPanel {session} />
		{:else if bottomPanelTab === 'lasers'}
			<LasersPanel {session} />
		{:else if bottomPanelTab === 'logs'}
			<div class="h-full overflow-hidden bg-card p-2">
				<LogViewer logs={app.logs} onClear={() => app.clearLogs()} />
			</div>
		{/if}
	</Pane>
</PaneGroup>
<footer class="flex items-center justify-between border-t border-border px-4 py-2">
	<ProfileSelector {session} size="sm" class="max-w-56" />
	<div class="flex divide-x divide-border rounded border border-border">
		<button onclick={() => selectTab('cameras')} class={tabClass(bottomPanelTab === 'cameras')}>Cameras</button>
		<button onclick={() => selectTab('lasers')} class={tabClass(bottomPanelTab === 'lasers')}>
			Lasers
			{#each Object.values(session.lasers) as laser (laser.deviceId)}
				<div class="relative">
					{#if laser.isEnabled}
						<div class="h-2 w-2 rounded-full" style="background-color: {laser.color};"></div>
						<span class="absolute inset-0 animate-ping rounded-full opacity-75" style="background-color: {laser.color};"
						></span>
					{:else}
						<div class="h-2 w-2 rounded-full border opacity-70" style="border-color: {laser.color};"></div>
					{/if}
				</div>
			{/each}
		</button>
		<button onclick={() => selectTab('logs')} class={tabClass(bottomPanelTab === 'logs')}>Logs</button>
	</div>
</footer>
