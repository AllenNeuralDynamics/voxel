<script lang="ts">
	import { getSessionContext } from '$lib/context';
	import { ProfileInfoPopover, ProfileStatus } from '$lib/ui/profile';
	import { GridControls } from '$lib/ui/grid';
	import { Dialog } from '$lib/ui/kit';
	import { sanitizeString } from '$lib/utils';
	import { Plus, TrashCanOutline } from '$lib/icons';
	import { tv } from 'tailwind-variants';
	import { watch } from 'runed';

	const session = getSessionContext();

	const profilePill = tv({
		base: 'rounded-xl border border-border px-3 py-1.5 text-[0.65rem] uppercase tracking-wide transition-colors',
		variants: {
			phantom: { true: 'border-dashed' },
			selected: { true: '' }
		},
		compoundVariants: [
			{ phantom: true, selected: true, class: 'border-amber-400/60 bg-amber-950/40 text-amber-200' },
			{
				phantom: true,
				selected: false,
				class: 'border-amber-400/30 bg-surface text-amber-400/60 hover:bg-amber-950/20 hover:text-amber-200'
			},
			{ phantom: false, selected: true, class: 'border-ring bg-muted text-foreground' },
			{
				phantom: false,
				selected: false,
				class: 'bg-surface text-muted-foreground hover:bg-muted hover:text-foreground'
			}
		]
	});

	// Selected tab auto-follows the active profile
	let selectedTab = $state<string | null>(null);

	watch(
		() => session.activeProfileId,
		(activeId) => {
			if (activeId) selectedTab = activeId;
		}
	);

	const acqIds = $derived(session.acquisitionProfileIds);
	const scoutLocked = $derived(session.workflow.stepStates['scout'] === 'committed');

	const phantomId = $derived.by(() => {
		const active = session.activeProfileId;
		return active != null && !acqIds.includes(active) ? active : null;
	});

	const tabIds = $derived(phantomId ? [...acqIds, phantomId] : acqIds);

	const activeTab = $derived.by(() => {
		return tabIds.includes(selectedTab ?? '') ? selectedTab! : (tabIds[0] ?? null);
	});

	const activeTabLabel = $derived(
		activeTab ? (session.config.profiles[activeTab]?.label ?? sanitizeString(activeTab)) : ''
	);
	const isActiveInPlan = $derived(activeTab ? activeTab in session.plan.grid_configs : false);

	let addDialogOpen = $state(false);
	let removeDialogOpen = $state(false);

	function confirmAddToPlan() {
		if (!activeTab) return;
		session.addAcquisitionProfile(activeTab);
		addDialogOpen = false;
	}

	function confirmRemoveFromPlan() {
		if (!activeTab) return;
		session.removeAcquisitionProfile(activeTab);
		selectedTab = null;
		removeDialogOpen = false;
	}
</script>

<div class="flex h-full flex-col justify-between">
	<div class="space-y-3 p-4">
		<!-- Profile pill tabs + actions -->
		<div class="flex flex-wrap items-center gap-2">
			{#each tabIds as pid (pid)}
				<button
					class={profilePill({ phantom: pid === phantomId, selected: pid === activeTab })}
					onclick={() => {
						selectedTab = pid;
					}}
				>
					{session.config.profiles[pid]?.label ?? sanitizeString(pid)}
				</button>
			{/each}
			{#if activeTab}
				<div class="ml-auto flex items-center gap-1.5">
					<ProfileStatus {session} profileId={activeTab} size="sm" />
					<ProfileInfoPopover {session} profileId={activeTab} size="sm" />
					{#if !scoutLocked}
						{#if isActiveInPlan}
							<button
								onclick={() => (removeDialogOpen = true)}
								class="rounded-lg px-1 py-0.5 text-muted-foreground transition-colors hover:bg-danger/10 hover:text-danger"
								title="Remove from plan"
							>
								<TrashCanOutline width="16" height="16" />
							</button>
						{:else}
							<button
								onclick={() => (addDialogOpen = true)}
								class="rounded-lg px-1 py-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
								title="Add to plan"
							>
								<Plus width="16" height="16" />
							</button>
						{/if}
					{/if}
				</div>
			{/if}
		</div>

		<!-- Grid controls -->
		{#if activeTab && acqIds.includes(activeTab)}
			<GridControls {session} profileId={activeTab} />
		{/if}
	</div>
</div>

<!-- Add to plan confirmation -->
<Dialog.Root bind:open={addDialogOpen}>
	<Dialog.Portal>
		<Dialog.Overlay />
		<Dialog.Content>
			<Dialog.Header>
				<Dialog.Title>Add to plan</Dialog.Title>
				<Dialog.Description>
					Add <strong>{activeTabLabel}</strong> to the acquisition plan? A default grid configuration will be created for
					this profile.
				</Dialog.Description>
			</Dialog.Header>
			<Dialog.Footer>
				<button
					onclick={() => (addDialogOpen = false)}
					class="rounded border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
				>
					Cancel
				</button>
				<button
					onclick={confirmAddToPlan}
					class="rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground transition-colors hover:bg-primary/90"
				>
					Add
				</button>
			</Dialog.Footer>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<!-- Remove from plan confirmation -->
<Dialog.Root bind:open={removeDialogOpen}>
	<Dialog.Portal>
		<Dialog.Overlay />
		<Dialog.Content>
			<Dialog.Header>
				<Dialog.Title>Remove from plan</Dialog.Title>
				<Dialog.Description>
					Remove <strong>{activeTabLabel}</strong> from the acquisition plan? Grid configuration and stacks for this profile
					will be discarded.
				</Dialog.Description>
			</Dialog.Header>
			<Dialog.Footer>
				<button
					onclick={() => (removeDialogOpen = false)}
					class="rounded border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
				>
					Cancel
				</button>
				<button
					onclick={confirmRemoveFromPlan}
					class="rounded bg-danger px-3 py-1.5 text-xs text-white transition-colors hover:bg-danger/90"
				>
					Remove
				</button>
			</Dialog.Footer>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
