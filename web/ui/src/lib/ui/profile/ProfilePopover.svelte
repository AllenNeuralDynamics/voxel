<script lang="ts">
	import type { Session } from '$lib/main';
	import { Popover } from 'bits-ui';
	import { ChevronDown, Plus, TrashCanOutline } from '$lib/icons';
	import { sanitizeString } from '$lib/utils';

	type Size = 'sm' | 'md' | 'lg';

	interface Props {
		session: Session;
		profileId: string;
		size?: Size;
		locked?: boolean;
		onRemove?: () => void;
	}

	let { session, profileId, size = 'sm', locked = false, onRemove }: Props = $props();

	const iconSize: Record<Size, string> = {
		sm: '16',
		md: '18',
		lg: '20'
	};

	const config = $derived(session.config);
	const profile = $derived(config.profiles[profileId]);
	const isInPlan = $derived(profileId in session.plan.grid_configs);

	let open = $state(false);
</script>

{#if profile}
	<Popover.Root bind:open>
		<Popover.Trigger
			class="rounded-lg px-1 py-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
		>
			<ChevronDown width={iconSize[size]} height={iconSize[size]} />
		</Popover.Trigger>
		<Popover.Portal>
			<Popover.Content
				class="z-50 w-72 rounded-xl border border-border bg-popover p-4 text-popover-foreground shadow-md"
				side="bottom"
				align="end"
				sideOffset={6}
			>
				{#if profile.desc}
					<p class="text-xs">{profile.desc}</p>
				{/if}
				{#if profile.channels.length > 0}
					<p class="text-xs {profile.desc ? 'mt-1.5' : ''} text-muted-foreground">
						{#each profile.channels as chId, i (chId)}{#if i > 0}, {/if}{config.channels[chId]?.label ?? sanitizeString(chId)}{/each}
					</p>
				{/if}
				{#if !locked}
					<div class="mt-3 border-t border-border pt-2">
						{#if isInPlan}
							<button
								onclick={() => {
									open = false;
									onRemove?.();
								}}
								class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-danger transition-colors hover:bg-danger/10"
							>
								<TrashCanOutline width="14" height="14" />
								Remove from plan
							</button>
						{:else}
							<button
								onclick={() => {
									session.addAcquisitionProfile(profileId);
									open = false;
								}}
								class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-foreground transition-colors hover:bg-muted"
							>
								<Plus width="14" height="14" />
								Add to plan
							</button>
						{/if}
					</div>
				{/if}
			</Popover.Content>
		</Popover.Portal>
	</Popover.Root>
{/if}
