<script lang="ts">
	import { getSessionContext } from '$lib/context';
	import { Button } from '$lib/ui/kit';
	import { Pane, PaneGroup } from 'paneforge';
	import PaneDivider from '$lib/ui/kit/PaneDivider.svelte';
	import { cn } from '$lib/utils';
	import { Crosshair, TrashCanOutline, ImageLight, PencilOutline } from '$lib/icons';
	import { ElementSize } from 'runed';
	import type { Snapshot } from '$lib/main';

	const session = getSessionContext();
	const snaps = $derived(session.snaps);

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

	// --- Inline rename ---

	let editingId = $state<string | null>(null);
	let editValue = $state('');

	function startRename(snap: Snapshot) {
		editingId = snap.id;
		editValue = snap.label;
	}

	function commitRename() {
		if (editingId && editValue.trim()) {
			snaps.rename(editingId, editValue.trim());
		}
		editingId = null;
	}

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
			<div class="flex-1 overflow-y-auto">
				{#if snaps.size === 0}
					<div class="flex h-full items-center justify-center p-4">
						<p class="text-center text-sm text-fg-faint">No snapshots yet</p>
					</div>
				{:else}
					<div class="space-y-px">
						{#each snaps.list as snap (snap.id)}
							{@const isSelected = snaps.selectedId === snap.id}
							<!-- svelte-ignore a11y_no_static_element_interactions -->
							<div
								class={cn(
									'flex w-full cursor-pointer items-start gap-2.5 px-3 py-2 text-left transition-colors',
									isSelected ? 'bg-element-selected' : 'hover:bg-element-hover'
								)}
								onclick={() => snaps.select(snap.id)}
							>
								<!-- Thumbnail -->
								<img
									src={snap.thumbnail}
									alt={snap.label}
									class="h-12 w-16 shrink-0 rounded border border-border object-cover"
								/>

								<!-- Info -->
								<div class="flex min-w-0 flex-1 flex-col gap-0.5">
									{#if editingId === snap.id}
										<!-- Inline rename input -->
										<!-- svelte-ignore a11y_autofocus -->
										<input
											type="text"
											bind:value={editValue}
											autofocus
											class="w-full rounded border border-border bg-surface px-1 py-0.5 text-sm text-fg outline-none focus:border-fg-muted"
											onblur={commitRename}
											onkeydown={(e) => {
												if (e.key === 'Enter') commitRename();
												if (e.key === 'Escape') editingId = null;
											}}
											onclick={(e) => e.stopPropagation()}
										/>
									{:else}
										<span class="truncate text-sm text-fg">{snap.label}</span>
									{/if}
									<span class="font-mono text-xs text-fg-muted tabular-nums">
										{(snap.stageX_um / 1000).toFixed(3)}, {(snap.stageY_um / 1000).toFixed(3)}, {(
											snap.stageZ_um / 1000
										).toFixed(3)}
									</span>
								</div>

								<!-- Actions -->
								<div class="flex shrink-0 items-center gap-0.5">
									<button
										class="rounded p-0.5 text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
										title="Rename"
										onclick={(e) => {
											e.stopPropagation();
											startRename(snap);
										}}
									>
										<PencilOutline width="12" height="12" />
									</button>
									<button
										class="rounded p-0.5 text-fg-muted transition-colors hover:bg-danger/10 hover:text-danger"
										title="Delete"
										onclick={(e) => {
											e.stopPropagation();
											snaps.remove(snap.id);
										}}
									>
										<TrashCanOutline width="12" height="12" />
									</button>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</div>
	</Pane>
</PaneGroup>
