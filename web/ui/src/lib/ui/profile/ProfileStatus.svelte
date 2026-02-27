<script lang="ts">
	import type { Session } from '$lib/main';
	import { Button } from '$lib/ui/kit';

	type Size = 'sm' | 'md' | 'lg';

	interface Props {
		session: Session;
		profileId: string;
		size?: Size;
		class?: string;
	}

	let { session, profileId, size = 'sm', class: className }: Props = $props();

	// Match Button size classes exactly (h, px, text) + transparent border for identical box model
	const badgeClasses: Record<Size, string> = {
		sm: 'h-6 px-2 text-[0.65rem] border border-transparent',
		md: 'h-7 px-3 text-[0.65rem] border border-transparent',
		lg: 'h-8 px-3 text-xs border border-transparent'
	};

	const buttonSize: Record<Size, 'xs' | 'sm' | 'md'> = {
		sm: 'xs',
		md: 'sm',
		lg: 'md'
	};

	const isActive = $derived(profileId === session.activeProfileId);
</script>

<!-- Grid overlap: both states occupy the same cell so the container sizes to the larger one -->
<div class="grid {className}">
	<span
		class="col-start-1 row-start-1 inline-flex items-center justify-center rounded-full bg-success/15 font-medium text-success {badgeClasses[size]}"
		class:invisible={!isActive}
	>
		Active
	</span>
	<div class="col-start-1 row-start-1 flex items-center justify-center" class:invisible={isActive}>
		<Button
			size={buttonSize[size]}
			variant="outline"
			class="rounded-full"
			onclick={() => session.activateProfile(profileId)}
			disabled={session.isMutating}
		>
			Activate
		</Button>
	</div>
</div>
