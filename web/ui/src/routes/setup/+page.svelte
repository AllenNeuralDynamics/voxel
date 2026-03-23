<script lang="ts">
	import { getSessionContext } from '$lib/context';
	import { Button, Dialog } from '$lib/ui/kit';
	import { sanitizeString } from '$lib/utils';
	import { TrashCanOutline } from '$lib/icons';
	import { watch } from 'runed';

	const session = getSessionContext();

	// Selected tab auto-follows the active profile
	let selectedTab = $state<string | null>(null);

	watch(
		() => session.activeProfileId,
		(activeId) => {
			if (activeId) selectedTab = activeId;
		}
	);

	const tabIds = $derived(Object.keys(session.config.profiles));

	const activeTab = $derived.by(() => {
		return tabIds.includes(selectedTab ?? '') ? selectedTab! : (tabIds[0] ?? null);
	});

	const activeTabLabel = $derived(
		activeTab ? (session.config.profiles[activeTab]?.label ?? sanitizeString(activeTab)) : ''
	);
	const activeTabStacks = $derived(activeTab ? session.stacks.filter((s) => s.profile_id === activeTab) : []);

	let clearDialogOpen = $state(false);

	function confirmClearStacks() {
		if (!activeTab || activeTabStacks.length === 0) return;
		session.removeStacks(activeTabStacks.map((s) => ({ row: s.row, col: s.col })));
		clearDialogOpen = false;
	}
	let activeProfile = $derived(session.config.profiles[session.activeProfileId ?? '']);
</script>

<div class="flex h-full flex-col">
	<div class="flex-1 space-y-3 px-6 py-2">
		{#if activeProfile}
			<div class="flex items-center justify-between gap-2">
				<div class="min-w-0 text-base">
					{#if activeProfile?.desc}
						<p class="text-fg">{activeProfile.desc}</p>
					{/if}
					{#if activeProfile?.channels.length}
						<p class="text-fg-muted flex flex-wrap items-center gap-x-1.5">
							<span>Channels:</span>
							{#each activeProfile.channels as chId, i (chId)}
								<span>
									{session.config.channels[chId]?.label ?? sanitizeString(chId)}
									{#if i < activeProfile.channels.length - 1},
									{/if}
								</span>
							{/each}
						</p>
					{/if}
				</div>
				<Button
					variant="ghost"
					size="xs"
					class="text-fg-muted shrink-0 hover:bg-danger/10 hover:text-danger"
					title="Clear all stacks"
					disabled={activeTabStacks.length < 1}
					onclick={() => (clearDialogOpen = true)}
				>
					<TrashCanOutline width="16" height="16" /> <span class="text-nowrap">Clear Stacks</span>
				</Button>
			</div>
			{@const gc = session.config.profiles[activeTab]?.grid}
			{#if gc}
				<p class="text-fg-muted text-sm">
					Offset: X {(gc.x_offset_um / 1000).toFixed(1)} mm, Y {(gc.y_offset_um / 1000).toFixed(1)} mm &middot; Overlap: X
					{gc.overlap_x.toFixed(2)}, Y {gc.overlap_y.toFixed(2)}
					{#if activeTabStacks.length > 0}
						&middot;
						<span class="text-info">{activeTabStacks.length} stack{activeTabStacks.length !== 1 ? 's' : ''}</span>
					{/if}
				</p>
			{/if}
		{/if}
	</div>
</div>

<!-- Clear all stacks confirmation -->
<Dialog.Root bind:open={clearDialogOpen}>
	<Dialog.Portal>
		<Dialog.Overlay />
		<Dialog.Content>
			<Dialog.Header>
				<Dialog.Title>Clear all stacks</Dialog.Title>
				<Dialog.Description>
					Remove all {activeTabStacks.length} stack{activeTabStacks.length !== 1 ? 's' : ''} for
					<strong>{activeTabLabel}</strong>? The profile will be removed from the acquisition plan.
				</Dialog.Description>
			</Dialog.Header>
			<Dialog.Footer>
				<button
					onclick={() => (clearDialogOpen = false)}
					class="text-fg-muted hover:bg-element-hover hover:text-fg rounded border border-border px-3 py-1.5 text-sm transition-colors"
				>
					Cancel
				</button>
				<button
					onclick={confirmClearStacks}
					class="rounded bg-danger px-3 py-1.5 text-sm text-danger-fg transition-colors hover:bg-danger/90"
				>
					Clear
				</button>
			</Dialog.Footer>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<style>
	@keyframes pulse-info-bg {
		0%,
		100% {
			box-shadow: inset 0 0 0 100px color-mix(in oklch, var(--info) 0%, transparent);
		}
		50% {
			box-shadow: inset 0 0 0 100px color-mix(in oklch, var(--info) 12%, transparent);
		}
	}

	:global(.pill-pulse-info) {
		animation: pulse-info-bg 3s ease-in-out infinite;
	}
</style>
