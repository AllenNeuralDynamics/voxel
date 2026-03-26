<script lang="ts" module>
	let savedTab = 'lasers';
</script>

<script lang="ts">
	import { getSessionContext, getLogsContext } from '$lib/context';
	import { cn } from '$lib/utils';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import LogViewer from '$lib/ui/LogViewer.svelte';
	import LasersPanel from '$lib/ui/LasersPanel.svelte';
	import CamerasPanel from '$lib/ui/CamerasPanel.svelte';
	import AuxDevicesPanel from '$lib/ui/AuxDevicesPanel.svelte';

	let { children } = $props();

	const session = getSessionContext();
	const { logs, clearLogs } = $derived(getLogsContext());

	let bottomPanelTab = $state(savedTab);
	$effect(() => {
		savedTab = bottomPanelTab;
	});
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
			'gap-2 flex items-center h-ui-xs px-2 text-sm transition-colors hover:bg-element-hover',
			selected ? 'bg-element-bg text-fg' : 'text-fg-muted'
		);
	}
</script>

<PaneGroup direction="vertical" autoSaveId="workflow-v">
	<Pane>
		<div class="overflow auto flex h-full flex-col">
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
		defaultSize={40}
		minSize={30}
		maxSize={50}
		onCollapse={() => {}}
	>
		{#if bottomPanelTab === 'devices'}
			<AuxDevicesPanel {session} class="overflow-auto p-2" />
		{:else if bottomPanelTab === 'cameras'}
			<CamerasPanel {session} class="h-full" />
		{:else if bottomPanelTab === 'lasers'}
			<LasersPanel {session} />
		{:else if bottomPanelTab === 'logs'}
			<div class="h-full overflow-hidden bg-card p-2">
				<LogViewer {logs} onClear={clearLogs} />
			</div>
		{/if}
	</Pane>
</PaneGroup>
<footer class="flex h-ui-xl items-center justify-between border-t border-border px-4 py-2">
	<div class="flex divide-x divide-border rounded border border-border">
		<button onclick={() => selectTab('devices')} class={tabClass(bottomPanelTab === 'devices')}>Auxiliary</button>
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
	</div>
	<div class="flex divide-x divide-border rounded border border-border">
		<button onclick={() => selectTab('logs')} class={tabClass(bottomPanelTab === 'logs')}>Logs</button>
	</div>
</footer>
