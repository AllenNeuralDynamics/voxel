<script lang="ts">
	import { getLogsContext } from '$lib/context';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import LogViewer from '$lib/ui/LogViewer.svelte';

	let { children } = $props();

	const { logs, clearLogs } = $derived(getLogsContext());

	let logPane: Pane | undefined = $state(undefined);
</script>

<PaneGroup direction="vertical" autoSaveId="acquisition-v">
	<Pane class="flex flex-col">
		<div class="flex-1 overflow-auto">
			{@render children()}
		</div>
	</Pane>
	<PaneDivider
		direction="horizontal"
		ondblclick={() => {
			if (logPane?.isCollapsed()) logPane.expand();
			else logPane?.collapse();
		}}
	/>
	<Pane
		bind:this={logPane}
		collapsible
		collapsedSize={0}
		defaultSize={30}
		minSize={20}
		maxSize={50}
		onCollapse={() => {}}
	>
		<div class="h-full overflow-hidden bg-card p-2">
			<LogViewer {logs} onClear={clearLogs} />
		</div>
	</Pane>
</PaneGroup>
