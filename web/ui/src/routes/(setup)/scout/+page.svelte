<script lang="ts">
	import { getSessionContext } from '$lib/context';
	import type { Snapshot } from '$lib/main/snapshots.svelte';
	import { Button, ContextMenu, Rename } from '$lib/ui/kit';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import { cn } from '$lib/utils';
	import { Crosshair, TrashCanOutline, ImageLight, InformationOutline } from '$lib/icons';
	import { ElementSize } from 'runed';

	const session = getSessionContext();
	const snaps = $derived(session.snaps);

	let renamingId = $state<string | null>(null);

	let canSnap = $derived(session.preview.isPreviewing || session.mode === 'acquiring');
	let showDetails = $state(true);

	let previewUrl = $state<string | null>(null);
	let prevBlobRef: Blob | null = null;

	$effect(() => {
		const focused = snaps.focused;
		if (focused && focused.blob !== prevBlobRef) {
			if (previewUrl) URL.revokeObjectURL(previewUrl);
			previewUrl = URL.createObjectURL(focused.blob);
			prevBlobRef = focused.blob;
		} else if (!focused) {
			if (previewUrl) URL.revokeObjectURL(previewUrl);
			previewUrl = null;
			prevBlobRef = null;
		}
	});

	function handleClick(e: MouseEvent, id: string) {
		if (e.ctrlKey || e.metaKey) {
			snaps.sel.toggle(id);
		} else if (e.shiftKey) {
			snaps.sel.rangeSelect(id);
		} else {
			snaps.sel.select(id);
		}
	}

	function handleKeydown(e: KeyboardEvent, id: string) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			snaps.sel.select(id);
		}
	}

	const SIDEBAR_MIN_PX = 300;
	let paneGroupEl = $state<HTMLElement | null>(null);
	const paneGroupSize = new ElementSize(() => paneGroupEl);
</script>

{#snippet snapItem(snap: Snapshot)}
	{@const isSelected = snaps.sel.has(snap.id)}
	{@const snapPos = { x: snap.stageX, y: snap.stageY }}
	{@const snapPosMm = { x: snap.stageX / 1000, y: snap.stageY / 1000 }}
	<ContextMenu.Root>
		<ContextMenu.Trigger>
			<div
				role="option"
				tabindex="0"
				aria-selected={isSelected}
				class={cn(
					'flex w-full cursor-pointer items-start gap-2.5 px-3 py-2 text-left transition-colors outline-none select-none',
					snaps.sel.focused === snap.id
						? 'bg-element-selected'
						: isSelected
							? 'bg-element-hover'
							: 'hover:bg-element-hover focus-visible:bg-element-hover'
				)}
				onclick={(e) => handleClick(e, snap.id)}
				onkeydown={(e) => handleKeydown(e, snap.id)}
			>
				<!-- Thumbnail -->
				<img
					src={snap.thumbnail}
					alt={snap.label}
					class="h-12 w-16 shrink-0 rounded border border-border object-cover"
				/>

				<!-- Info -->
				<div class="flex min-w-0 flex-1 flex-col gap-0.5">
					<Rename
						value={snap.label}
						size="sm"
						class="text-fg"
						textClass="truncate"
						mode={renamingId === snap.id ? 'edit' : 'view'}
						onSave={(newLabel) => {
							snaps.rename(snap.id, newLabel);
							renamingId = null;
						}}
						onCancel={() => (renamingId = null)}
					/>
					<span class="font-mono text-xs text-fg-muted tabular-nums">
						{snapPosMm.x.toFixed(3)}, {snapPosMm.y.toFixed(3)}, {(snap.stageZ / 1000).toFixed(3)}
					</span>
				</div>

				<!-- Profile badge -->
				{#if snap.profileLabel}
					<span class="shrink-0 rounded bg-element-bg px-1.5 py-0.5 text-xs text-fg-muted">{snap.profileLabel}</span>
				{/if}
			</div>
		</ContextMenu.Trigger>
		<ContextMenu.Content>
			<ContextMenu.Item
				onSelect={() => {
					session.stage.moveXY(snapPos.x, snapPos.y);
					session.stage.moveZ(snap.stageZ);
				}}
			>
				Go to position
			</ContextMenu.Item>
			<ContextMenu.Item onSelect={() => (renamingId = snap.id)}>Rename</ContextMenu.Item>
			<ContextMenu.Separator />
			<ContextMenu.Sub>
				<ContextMenu.SubTrigger disabled={!session.gridEditable}>Align grid</ContextMenu.SubTrigger>
				<ContextMenu.SubContent>
					<ContextMenu.Item onSelect={() => session.alignGrid('top', snapPos)}>Top</ContextMenu.Item>
					<ContextMenu.Item onSelect={() => session.alignGrid('bottom', snapPos)}>Bottom</ContextMenu.Item>
					<ContextMenu.Item onSelect={() => session.alignGrid('left', snapPos)}>Left</ContextMenu.Item>
					<ContextMenu.Item onSelect={() => session.alignGrid('right', snapPos)}>Right</ContextMenu.Item>
					<ContextMenu.Separator />
					<ContextMenu.Item onSelect={() => session.alignGrid('center', snapPos)}>Center</ContextMenu.Item>
				</ContextMenu.SubContent>
			</ContextMenu.Sub>
			<ContextMenu.Separator />
			<ContextMenu.Item variant="destructive" onSelect={() => snaps.remove(snap.id)}>Delete</ContextMenu.Item>
		</ContextMenu.Content>
	</ContextMenu.Root>
{/snippet}

<PaneGroup bind:ref={paneGroupEl} direction="horizontal" autoSaveId="setup.scout" class="h-full">
	<Pane defaultSize={70} minSize={40}>
		<div class="relative flex h-full flex-col items-center justify-center overflow-hidden bg-canvas">
			{#if snaps.focused && previewUrl}
				<img src={previewUrl} alt={snaps.focused.label} class="max-h-full max-w-full object-contain" />

				<!-- Detail toggle -->
				<button
					class="absolute top-2 right-2 rounded-full p-1.5 transition-colors {showDetails
						? 'text-fg-muted'
						: 'text-fg-faint'} hover:text-fg"
					title={showDetails ? 'Hide details' : 'Show details'}
					onclick={() => (showDetails = !showDetails)}
				>
					<InformationOutline width="16" height="16" />
				</button>

				<!-- Floating detail panel -->
				{#if showDetails}
					{@const snap = snaps.focused}
					{@const channelEntries = Object.entries(snap.channels)}
					<div
						class="absolute bottom-3 left-3 max-w-[min(28rem,calc(100%-1.5rem))] rounded-lg border border-border/50 bg-surface/85 px-3 py-2.5 text-xs backdrop-blur-md"
					>
						<div class="mb-2 flex items-center justify-between gap-4">
							<span class="font-medium text-fg">{snap.label}</span>
							<span class="font-mono text-fg-muted tabular-nums">
								{(snap.stageX / 1000).toFixed(3)}, {(snap.stageY / 1000).toFixed(3)}, {(snap.stageZ / 1000).toFixed(3)} mm
							</span>
						</div>
						{#if channelEntries.length > 0}
							<div class="flex gap-3">
								{#each channelEntries as [name, ch] (name)}
									{@const color = session.preview.resolveColor(ch.colormap) ?? 'var(--color-fg-muted)'}
									<div class="min-w-0 flex-1 space-y-1">
										<div class="flex items-center gap-1.5">
											<span class="h-2 w-2 shrink-0 rounded-full" style:background-color={color}></span>
											<span class="truncate font-medium text-fg">{ch.label}</span>
										</div>
										{#if ch.detection}
											<div class="flex flex-wrap gap-x-2 text-fg-muted">
												{#if ch.detection.exposureTime != null}
													<span>{ch.detection.exposureTime} ms</span>
												{/if}
												{#if ch.detection.binning != null}
													<span>{ch.detection.binning}x</span>
												{/if}
											</div>
										{/if}
										{#if ch.illumination}
											<div class="flex flex-wrap gap-x-2 text-fg-muted">
												{#if ch.illumination.powerSetpoint != null}
													<span>{ch.illumination.powerSetpoint.toFixed(1)} mW</span>
												{/if}
											</div>
										{/if}
										<div
											class="h-1 rounded-full"
											style="background: linear-gradient(to right, transparent {ch.levelsMin * 100}%, {color} {ch.levelsMin * 100}%, {color} {ch.levelsMax * 100}%, transparent {ch.levelsMax * 100}%);"
										></div>
									</div>
								{/each}
							</div>
						{/if}
					</div>
				{/if}
			{:else}
				<div class="flex flex-col items-center gap-3 text-fg-faint">
					<Crosshair width="32" height="32" class="opacity-40" />
					<p class="text-sm">Move the stage and capture snapshots to explore your sample</p>
					<Button variant="outline" size="sm" disabled={!canSnap} onclick={() => session.snap()}>
						<ImageLight width="14" height="14" />
						Capture Snapshot
					</Button>
					{#if !canSnap}
						<span class="text-xs text-fg-faint">Start preview to capture snapshots</span>
					{/if}
				</div>
			{/if}
		</div>
	</Pane>

	<PaneDivider direction="vertical" />

	<Pane
		defaultSize={30}
		minSize={paneGroupSize.width > 0 ? (SIDEBAR_MIN_PX / paneGroupSize.width) * 100 : 25}
		maxSize={45}
	>
		<div class="flex h-full flex-col overflow-hidden">
			<!-- Header with capture button -->
			<div class="flex items-center justify-between border-b border-border px-3 py-2">
				<span class="text-xs text-fg-muted">
					{snaps.size} snapshot{snaps.size !== 1 ? 's' : ''}
				</span>
				<div class="flex items-center gap-1" title={canSnap ? undefined : 'Start preview to capture snapshots'}>
					{#if snaps.size > 0}
						<Button
							variant="ghost"
							size="xs"
							class="text-fg-muted hover:bg-danger/10 hover:text-danger"
							onclick={() => {
								if (snaps.sel.size > 1) {
									snaps.remove(snaps.sel.selection);
								} else {
									snaps.clear();
								}
							}}
						>
							<TrashCanOutline width="14" height="14" />
							{snaps.sel.size > 1 ? `Clear ${snaps.sel.size}` : 'Clear all'}
						</Button>
					{/if}
					<Button variant="outline" size="xs" disabled={!canSnap} onclick={() => session.snap()}>
						<ImageLight width="14" height="14" />
						Snap
					</Button>
				</div>
			</div>

			<div class="flex-1 overflow-y-auto" role="listbox" aria-label="Snapshots" aria-multiselectable="true">
				{#if snaps.size === 0}
					<div class="flex h-full items-center justify-center p-4">
						<p class="text-center text-sm text-fg-faint">No snapshots yet</p>
					</div>
				{:else}
					<div class="space-y-px">
						{#each snaps.list as snap (snap.id)}
							{@render snapItem(snap)}
						{/each}
					</div>
				{/if}
			</div>
		</div>
	</Pane>
</PaneGroup>
