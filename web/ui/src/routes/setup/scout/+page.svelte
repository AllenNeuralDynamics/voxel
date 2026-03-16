<script lang="ts">
	import { getSessionContext } from '$lib/context';
	import { ProfileStatus } from '$lib/ui/profile';
	import { GridControls } from '$lib/ui/grid';
	import { Button, Dialog } from '$lib/ui/kit';
	import { sanitizeString } from '$lib/utils';
	import { Plus, TrashCanOutline } from '$lib/icons';
	import { tv } from 'tailwind-variants';
	import { watch } from 'runed';

	const session = getSessionContext();

	const profilePill = tv({
		base: 'rounded-xl border border-fg-faint px-3 py-1.5 text-xs uppercase tracking-wide text-fg transition-colors',
		variants: {
			inPlan: {
				true: '',
				false: 'border-dashed'
			},
			selected: {
				true: 'outline outline-1 outline-fg-muted',
				false: 'hover:bg-element-hover'
			}
		}
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
	const tabIds = $derived(Object.keys(session.config.profiles));
	const planIds = $derived(tabIds.filter((id) => acqIds.includes(id)));
	const availableIds = $derived(tabIds.filter((id) => !acqIds.includes(id)));

	const activeTab = $derived.by(() => {
		return tabIds.includes(selectedTab ?? '') ? selectedTab! : (tabIds[0] ?? null);
	});

	const activeTabLabel = $derived(
		activeTab ? (session.config.profiles[activeTab]?.label ?? sanitizeString(activeTab)) : ''
	);
	const isActiveInPlan = $derived(activeTab ? acqIds.includes(activeTab) : false);

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
		removeDialogOpen = false;
	}
</script>

<div class="flex h-full flex-col">
	<!-- <div class="space-y-3"> -->
	<!-- Profile pill tabs: in-plan | divider | available -->
	<div class="bg-elevated flex items-center gap-2 border-b border-border px-6 py-2.5">
		<div class="flex flex-wrap items-center gap-2">
			{#each planIds as pid (pid)}
				{@const isHwActive = session.activeProfileId === pid}
				<button
					class="{profilePill({ inPlan: true, selected: pid === activeTab })} {isHwActive ? 'pill-pulse-info' : ''}"
					onclick={() => {
						selectedTab = pid;
					}}
				>
					{session.config.profiles[pid]?.label ?? sanitizeString(pid)}
				</button>
			{:else}
				<span class="text-xs text-fg-muted italic">No profiles added to plan</span>
			{/each}
		</div>

		{#if availableIds.length > 0}
			<div class="bg-fg-faint mx-3 h-5 w-px shrink-0"></div>

			<div class="flex flex-wrap items-center gap-2">
				{#each availableIds as pid (pid)}
					{@const isHwActive = session.activeProfileId === pid}
					<button
						class="{profilePill({ inPlan: false, selected: pid === activeTab })} {isHwActive
							? 'pill-pulse-neutral'
							: ''}"
						onclick={() => {
							selectedTab = pid;
						}}
					>
						{session.config.profiles[pid]?.label ?? sanitizeString(pid)}
					</button>
				{/each}
			</div>
		{/if}
	</div>

	<div class="flex-1 space-y-3 px-6 py-2">
		<!-- Active tab info + actions -->
		{#if activeTab}
			{@const profile = session.config.profiles[activeTab]}
			<div class="flex items-center justify-between gap-2">
				<div class="min-w-0 text-base">
					{#if profile?.desc}
						<p class="text-fg">{profile.desc}</p>
					{/if}
					{#if profile?.channels.length}
						<p class="text-fg-muted flex flex-wrap items-center gap-x-1.5">
							<span>Channels:</span>
							{#each profile.channels as chId, i (chId)}
								<span
									>{session.config.channels[chId]?.label ??
										sanitizeString(chId)}{#if i < profile.channels.length - 1},{/if}</span
								>
							{/each}
						</p>
					{/if}
				</div>
				<div class="flex items-center gap-2">
					{#if isActiveInPlan}
						<Button
							variant="ghost"
							size="icon-xs"
							class="text-fg-muted shrink-0 hover:bg-danger/10 hover:text-danger"
							title="Remove from plan"
							disabled={scoutLocked}
							onclick={() => (removeDialogOpen = true)}
						>
							<TrashCanOutline width="16" height="16" />
						</Button>
					{/if}
					<ProfileStatus {session} profileId={activeTab} size="sm" />
				</div>
			</div>
			<!-- Grid controls -->
			{#if acqIds.includes(activeTab)}
				<GridControls {session} profileId={activeTab} />
			{:else}
				<div class="grid h-full place-content-center">
					<div class="text-fg-muted flex flex-col items-center justify-center gap-4 py-12 text-center text-sm">
						<p>
							Add <span class="text-fg">{activeTabLabel}</span> to the plan to configure its grid and stacks.
						</p>
						<Button variant="outline" size="sm" disabled={scoutLocked} onclick={() => (addDialogOpen = true)}>
							<Plus width="14" height="14" />
							Add to plan
						</Button>
					</div>
				</div>
			{/if}
		{/if}
	</div>
	<!-- </div> -->
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
					class="text-fg-muted hover:bg-element-hover hover:text-fg rounded border border-border px-3 py-1.5 text-sm transition-colors"
				>
					Cancel
				</button>
				<button
					onclick={confirmAddToPlan}
					class="text-primary-fg rounded bg-primary px-3 py-1.5 text-sm transition-colors hover:bg-primary/90"
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
					class="text-fg-muted hover:bg-element-hover hover:text-fg rounded border border-border px-3 py-1.5 text-sm transition-colors"
				>
					Cancel
				</button>
				<button
					onclick={confirmRemoveFromPlan}
					class="rounded bg-danger px-3 py-1.5 text-sm text-danger-fg transition-colors hover:bg-danger/90"
				>
					Remove
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

	@keyframes pulse-neutral-bg {
		0%,
		100% {
			box-shadow: inset 0 0 0 100px transparent;
		}
		50% {
			box-shadow: inset 0 0 0 100px var(--element-hover);
		}
	}

	:global(.pill-pulse-info) {
		animation: pulse-info-bg 3s ease-in-out infinite;
	}

	:global(.pill-pulse-neutral) {
		animation: pulse-neutral-bg 3s ease-in-out infinite;
	}
</style>
