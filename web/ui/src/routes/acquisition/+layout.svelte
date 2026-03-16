<script lang="ts">
	import { getLogsContext } from '$lib/context';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import LogViewer from '$lib/ui/LogViewer.svelte';
	import { getSessionContext } from '$lib/context';
	import { Button } from '$lib/ui/kit';
	import { ChevronLeft } from '$lib/icons';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';

	let { children } = $props();

	const { logs, clearLogs } = $derived(getLogsContext());

	let logPane: Pane | undefined = $state(undefined);
	const session = getSessionContext();
</script>

<PaneGroup direction="vertical" autoSaveId="acquisition-v">
	<Pane class="flex flex-col justify-between">
		<div class="overflow-auto">
			{@render children()}
		</div>
		<div class="align-center mb-2 flex justify-between gap-4 px-3 py-2">
			{#if session.workflow.allCommitted}
				<Button
					variant="outline"
					size="sm"
					onclick={async () => {
						const stepId = await session.workflowBack();
						if (stepId) goto(resolve(`/workflow/${stepId}`), { keepFocus: true, noScroll: true });
					}}
				>
					<ChevronLeft width="12" height="12" /> Back to setup
				</Button>
			{/if}
			{#if session.info}
				<div class="text-fg-muted ml-auto text-sm">
					<!-- <span class="text-fg">{session.info.rig_name}</span> -->
					{#if session.info.session_name}
						<span class="mx-1.5 text-border">·</span>
						<span>{session.info.session_name}</span>
					{/if}
					<span class="mx-1.5 text-border">·</span>
					<span class="truncate" title={session.info.session_dir}>{session.info.session_dir}</span>
				</div>
			{/if}
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
