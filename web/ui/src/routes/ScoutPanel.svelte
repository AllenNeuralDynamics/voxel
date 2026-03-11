<script lang="ts">
	import type { Session } from '$lib/main';
	import { ProfilePopover, ProfileStatus } from '$lib/ui/profile';
	import { GridControls } from '$lib/ui/grid/canvas';
	import { sanitizeString } from '$lib/utils';
	import { tv } from 'tailwind-variants';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

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

	$effect(() => {
		const activeId = session.activeProfileId;
		if (activeId) selectedTab = activeId;
	});

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
					<ProfilePopover
						{session}
						profileId={activeTab}
						size="sm"
						locked={scoutLocked}
						onRemove={() => {
							session.removeAcquisitionProfile(activeTab);
							selectedTab = null;
						}}
					/>
				</div>
			{/if}
		</div>

		<!-- Grid controls -->
		{#if activeTab && acqIds.includes(activeTab)}
			<GridControls {session} profileId={activeTab} />
		{/if}
	</div>
</div>
