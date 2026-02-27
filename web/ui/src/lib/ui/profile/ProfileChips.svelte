<script lang="ts">
	import type { Session } from '$lib/main';
	import { sanitizeString } from '$lib/utils';
	import { Button } from '$lib/ui/kit';

	interface Props {
		session: Session;
		profileId: string;
		showStatus?: boolean;
		class?: string;
	}

	let { session, profileId, showStatus = false, class: className }: Props = $props();

	const config = $derived(session.config);
	const isActive = $derived(profileId === session.activeProfileId);
	const profile = $derived(config.profiles[profileId]);
</script>

{#if profile}
	<div class="flex items-center gap-1.5 {className}">
		{#each profile.channels as chId (chId)}
			<span class="rounded-full bg-muted px-1.5 py-px text-[0.65rem] text-foreground">
				{config.channels[chId]?.label ?? sanitizeString(chId)}
			</span>
		{/each}
		{#if showStatus}
			{#if isActive}
				<span
					class="inline-flex h-6 items-center justify-center rounded-full bg-success/15 px-3.5 text-[0.65rem] font-medium text-success"
				>
					Active
				</span>
			{:else}
				<Button
					size="xs"
					variant="outline"
					class="rounded-full"
					onclick={() => session.activateProfile(profileId)}
					disabled={session.isMutating}
				>
					Activate
				</Button>
			{/if}
		{/if}
	</div>
{/if}
