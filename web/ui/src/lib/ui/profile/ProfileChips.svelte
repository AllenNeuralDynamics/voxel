<script lang="ts">
	import type { Session } from '$lib/main';
	import { sanitizeString } from '$lib/utils';

	type Size = 'sm' | 'md' | 'lg';

	interface Props {
		session: Session;
		profileId: string;
		size?: Size;
		class?: string;
	}

	let { session, profileId, size = 'sm', class: className }: Props = $props();

	const sizeClasses: Record<Size, string> = {
		sm: 'px-1.5 py-px text-[0.65rem]',
		md: 'px-3 py-1 text-xs',
		lg: 'px-3.5 py-1.5 text-sm'
	};

	const config = $derived(session.config);
	const profile = $derived(config.profiles[profileId]);
</script>

{#if profile}
	<div class="flex items-center gap-1.5 {className}">
		{#each profile.channels as chId (chId)}
			<span class="rounded-full bg-muted text-foreground {sizeClasses[size]}">
				{config.channels[chId]?.label ?? sanitizeString(chId)}
			</span>
		{/each}
	</div>
{/if}
