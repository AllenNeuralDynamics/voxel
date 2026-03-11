<script lang="ts">
	import { getAppContext } from '$lib/context';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import LogViewer from '$lib/ui/LogViewer.svelte';

	let { children } = $props();

	const app = getAppContext();

	let logPane: Pane | undefined = $state(undefined);
</script>

<PaneGroup direction="vertical" autoSaveId="acquire-v">
	<Pane>
		<div class="h-full overflow-auto">
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
			<LogViewer logs={app.logs} onClear={() => app.clearLogs()} />
		</div>
	</Pane>
</PaneGroup>
