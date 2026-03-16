<script lang="ts">
	import type { Session } from '$lib/main';

	type Size = 'sm' | 'md' | 'lg';

	interface Props {
		session: Session;
		profileId: string;
		size?: Size;
		class?: string;
	}

	let { session, profileId, size = 'sm', class: className }: Props = $props();

	const sizeClasses: Record<Size, string> = {
		sm: 'h-ui-sm w-20 text-xs',
		md: 'h-ui-md w-24 text-xs',
		lg: 'h-ui-lg w-28 text-sm'
	};

	const isActive = $derived(profileId === session.activeProfileId);
</script>

<button
	class="inline-flex items-center justify-center rounded-full border font-medium transition-colors {sizeClasses[
		size
	]} {isActive
		? 'border-success bg-success/15 text-success'
		: 'bg-warning-bg cursor-pointer border-warning text-warning hover:bg-warning/15'} {className}"
	onclick={() => session.activateProfile(profileId)}
	disabled={isActive || session.isSwitchingProfile}
>
	{isActive ? 'Active' : 'Activate'}
</button>
