<script lang="ts">
	import { getSessionContext } from '$lib/context';
	import { Button, ContextMenu, Rename } from '$lib/ui/kit';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import { cn } from '$lib/utils';
	import { Crosshair, TrashCanOutline, ImageLight } from '$lib/icons';
	import { ElementSize } from 'runed';

	const session = getSessionContext();
	const snaps = $derived(session.snaps);

	let renamingId = $state<string | null>(null);

	// --- Selected snapshot preview URL ---

	let previewUrl = $state<string | null>(null);
	let prevBlobRef: Blob | null = null;

	$effect(() => {
		const selected = snaps.selected;
		if (selected && selected.blob !== prevBlobRef) {
			if (previewUrl) URL.revokeObjectURL(previewUrl);
			previewUrl = URL.createObjectURL(selected.blob);
			prevBlobRef = selected.blob;
		} else if (!selected) {
			if (previewUrl) URL.revokeObjectURL(previewUrl);
			previewUrl = null;
			prevBlobRef = null;
		}
	});

	// --- Pane sizing ---

	const SIDEBAR_MIN_PX = 300;
	let paneGroupEl = $state<HTMLElement | null>(null);
	const paneGroupSize = new ElementSize(() => paneGroupEl);
</script>

<PaneGroup bind:ref={paneGroupEl} direction="horizontal" autoSaveId="scout-h" class="h-full">
	<!-- Main area: snapshot preview -->
	<Pane minSize={40}>
		<div class="flex h-full flex-col items-center justify-center overflow-hidden bg-canvas">
			{#if snaps.selected && previewUrl}
				<img src={previewUrl} alt={snaps.selected.label} class="max-h-full max-w-full object-contain" />
			{:else}
				<div class="flex flex-col items-center gap-3 text-fg-faint">
					<Crosshair width="32" height="32" class="opacity-40" />
					<p class="text-sm">Move the stage and capture snapshots to explore your sample</p>
					<Button variant="outline" size="sm" onclick={() => session.snap()}>
						<ImageLight width="14" height="14" />
						Capture Snapshot
					</Button>
				</div>
			{/if}
		</div>
	</Pane>

	<PaneDivider direction="vertical" />

	<!-- Sidebar: snapshot list -->
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
				<div class="flex items-center gap-1">
					{#if snaps.size > 0}
						<Button
							variant="ghost"
							size="icon-xs"
							class="text-fg-muted hover:bg-danger/10 hover:text-danger"
							title="Clear all snapshots"
							onclick={() => snaps.clear()}
						>
							<TrashCanOutline width="14" height="14" />
						</Button>
					{/if}
					<Button variant="outline" size="xs" onclick={() => session.snap()}>
						<ImageLight width="14" height="14" />
						Snap
					</Button>
				</div>
			</div>

			<!-- Snapshot list -->
			<div class="flex-1 overflow-y-auto" role="listbox" aria-label="Snapshots">
				{#if snaps.size === 0}
					<div class="flex h-full items-center justify-center p-4">
						<p class="text-center text-sm text-fg-faint">No snapshots yet</p>
					</div>
				{:else}
					<div class="space-y-px">
						{#each snaps.list as snap (snap.id)}
							{@const isSelected = snaps.selectedId === snap.id}
							{@const snapPos = { x: snap.stageX_um / 1000, y: snap.stageY_um / 1000 }}
							<ContextMenu.Root>
								<ContextMenu.Trigger>
									<div
										role="option"
										tabindex="0"
										aria-selected={isSelected}
										class={cn(
											'flex w-full cursor-pointer items-start gap-2.5 px-3 py-2 text-left transition-colors outline-none',
											isSelected
												? 'bg-element-selected'
												: 'hover:bg-element-hover focus-visible:bg-element-hover'
										)}
										onclick={() => snaps.select(snap.id)}
										onkeydown={(e) => {
											if (e.key === 'Enter' || e.key === ' ') {
												e.preventDefault();
												snaps.select(snap.id);
											}
										}}
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
												{snapPos.x.toFixed(3)}, {snapPos.y.toFixed(3)}, {(
													snap.stageZ_um / 1000
												).toFixed(3)}
											</span>
										</div>

										<!-- Profile badge -->
										{#if snap.profileLabel}
											<span
												class="shrink-0 rounded bg-element-bg px-1.5 py-0.5 text-xs text-fg-muted"
												>{snap.profileLabel}</span
											>
										{/if}
									</div>
								</ContextMenu.Trigger>
								<ContextMenu.Content>
									<ContextMenu.Item
										onSelect={() => {
											session.stage.moveXY(snapPos.x, snapPos.y);
											session.stage.moveZ(snap.stageZ_um / 1000);
										}}
									>
										Go to position
									</ContextMenu.Item>
									<ContextMenu.Item onSelect={() => (renamingId = snap.id)}>
										Rename
									</ContextMenu.Item>
									<ContextMenu.Separator />
									<ContextMenu.Sub>
										<ContextMenu.SubTrigger disabled={!session.gridEditable}>
											Align grid
										</ContextMenu.SubTrigger>
										<ContextMenu.SubContent>
											<ContextMenu.Item onSelect={() => session.alignGrid('top', snapPos)}>
												Top
											</ContextMenu.Item>
											<ContextMenu.Item onSelect={() => session.alignGrid('bottom', snapPos)}>
												Bottom
											</ContextMenu.Item>
											<ContextMenu.Item onSelect={() => session.alignGrid('left', snapPos)}>
												Left
											</ContextMenu.Item>
											<ContextMenu.Item onSelect={() => session.alignGrid('right', snapPos)}>
												Right
											</ContextMenu.Item>
											<ContextMenu.Separator />
											<ContextMenu.Item onSelect={() => session.alignGrid('center', snapPos)}>
												Center
											</ContextMenu.Item>
										</ContextMenu.SubContent>
									</ContextMenu.Sub>
									<ContextMenu.Separator />
									<ContextMenu.Item
										variant="destructive"
										onSelect={() => snaps.remove(snap.id)}
									>
										Delete
									</ContextMenu.Item>
								</ContextMenu.Content>
							</ContextMenu.Root>
						{/each}
					</div>
				{/if}
			</div>
		</div>
	</Pane>
</PaneGroup>
