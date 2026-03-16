<script lang="ts" module>
	let savedTab = 'lasers';
</script>

<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { getSessionContext, getLogsContext } from '$lib/context';
	import { cn } from '$lib/utils';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import { Button } from '$lib/ui/kit';
	import { Check, LucideCircle } from '$lib/icons';
	import LogViewer from '$lib/ui/LogViewer.svelte';
	import LasersPanel from './LasersPanel.svelte';
	import CamerasPanel from './CamerasPanel.svelte';

	let { children } = $props();

	const session = getSessionContext();
	const { logs, clearLogs } = $derived(getLogsContext());

	// --- Workflow step navigation ---

	const workflow = $derived(session.workflow);

	// Current viewed step from URL: /workflow/scout, /workflow/plan, /workflow/[step]
	const viewedStepId = $derived(
		page.params.step ?? page.route.id?.split('/').pop() ?? workflow.activeStep?.id
	);

	const viewedIsCommitted = $derived(
		viewedStepId != null && workflow.stepStates[viewedStepId] === 'committed'
	);

	const canComplete = $derived(
		viewedStepId != null && workflow.stepStates[viewedStepId] === 'active'
	);

	const canRevert = $derived(
		viewedStepId != null && workflow.steps[workflow.committedIndex]?.id === viewedStepId
	);

	function gotoStep(id: string) {
		const path = id === 'acquisition' ? '/acquisition' : `/workflow/${id}`;
		goto(resolve(path as '/'), { keepFocus: true, noScroll: true });
	}

	async function handleComplete() {
		const stepId = await session.workflowNext();
		gotoStep(stepId ?? 'acquisition');
	}

	async function handleRevert() {
		const stepId = await session.workflowBack();
		if (stepId) gotoStep(stepId);
	}

	function stepTabClass(stepId: string): string {
		const isViewing = viewedStepId === stepId;
		return cn(
			'flex h-ui-sm items-center gap-1.5 rounded-full px-3 text-xs uppercase tracking-wide transition-colors',
			isViewing ? 'bg-element-bg text-fg' : 'text-fg-muted hover:bg-element-hover'
		);
	}

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
			'gap-2 flex items-center px-2 py-0.5 text-sm transition-colors hover:bg-element-hover',
			selected ? 'bg-element-bg text-fg' : 'text-fg-muted'
		);
	}
</script>

<PaneGroup direction="vertical" autoSaveId="workflow-v">
	<Pane>
		<div class="flex h-full flex-col">
			<div class="flex-1 overflow-auto">
				{@render children()}
			</div>
			<!-- Workflow step navigation bar -->
			<nav class="mx-auto my-4 flex w-fit items-stretch overflow-hidden rounded-full border border-border">
				<div class="grid auto-cols-fr grid-flow-col gap-1 bg-panel px-3 py-2">
					{#each workflow.steps as step (step.id)}
						{@const state = workflow.stepStates[step.id]}
						<button class={stepTabClass(step.id)} onclick={() => gotoStep(step.id)}>
							{#if state === 'committed'}
								<Check width="14" height="14" class="text-success" />
							{:else if state === 'active'}
								<LucideCircle width="10" height="10" class="text-info" />
							{:else}
								<LucideCircle width="10" height="10" />
							{/if}
							{step.label}
						</button>
					{/each}
				</div>

				<div class="flex items-stretch">
					{#if viewedIsCommitted}
						<button
							disabled={!canRevert}
							onclick={handleRevert}
							class="w-28 text-center text-xs font-medium uppercase tracking-wide text-danger transition-colors hover:bg-danger-bg disabled:pointer-events-none disabled:opacity-50"
						>
							Revert
						</button>
					{:else}
						<button
							disabled={!canComplete}
							onclick={handleComplete}
							class="w-28 text-center text-xs font-medium uppercase tracking-wide text-success transition-colors hover:bg-success-bg disabled:pointer-events-none disabled:opacity-50"
						>
							Complete
						</button>
					{/if}
				</div>
			</nav>
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
		{#if bottomPanelTab === 'cameras'}
			<CamerasPanel {session} />
		{:else if bottomPanelTab === 'lasers'}
			<LasersPanel {session} />
		{:else if bottomPanelTab === 'logs'}
			<div class="h-full overflow-hidden bg-card p-2">
				<LogViewer {logs} onClear={clearLogs} />
			</div>
		{/if}
	</Pane>
</PaneGroup>
<footer class="flex items-center justify-between border-t border-border px-4 py-2">
	<div class="flex divide-x divide-border rounded border border-border">
		<button onclick={() => selectTab('logs')} class={tabClass(bottomPanelTab === 'logs')}>Logs</button>
	</div>
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
	</div>
</footer>
