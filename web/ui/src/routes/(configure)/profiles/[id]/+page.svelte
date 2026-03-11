<script lang="ts">
	import { getAppContext } from '$lib/context';
	import { page } from '$app/state';
	import { ProfileConfig } from '$lib/ui/profile';

	const app = getAppContext();
	const session = $derived(app.session!);
	const profileId = $derived(page.params.id!);
</script>

{#if profileId in session.config.profiles}
	<ProfileConfig {session} {profileId} />
{/if}
