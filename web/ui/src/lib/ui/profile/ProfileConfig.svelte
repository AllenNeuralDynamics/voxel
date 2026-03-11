<script lang="ts">
	import { Tabs } from 'bits-ui';
	import type { Session } from '$lib/main';
	import { sanitizeString } from '$lib/utils';
	import { ProfileChips } from '$lib/ui/profile';
	import ProfileProperties from './ProfileProperties.svelte';
	import ProfileWaveforms from './ProfileWaveforms.svelte';

	interface Props {
		session: Session;
		profileId: string;
	}

	let { session, profileId }: Props = $props();

	const profile = $derived(session.config.profiles[profileId]);
	let activeTab = $state('waveforms');
</script>

{#if profile}
	<section class="space-y-4">
		<!-- Header -->
		<div>
			<div class="flex items-center gap-1.5">
				<h2 class="text-sm font-medium text-foreground">
					{profile.label ?? sanitizeString(profileId)}
				</h2>
				<ProfileChips {session} {profileId} class="ml-auto" />
			</div>
			{#if profile.desc}
				<p class="mt-1 text-xs text-muted-foreground">{profile.desc}</p>
			{/if}
		</div>

		<!-- Tabs -->
		<Tabs.Root bind:value={activeTab}>
			<Tabs.List class="inline-flex h-7 items-center gap-1 rounded-md bg-muted p-0.5 text-muted-foreground">
				<Tabs.Trigger
					value="waveforms"
					class="inline-flex items-center justify-center rounded-sm px-2.5 py-1 text-[0.65rem] font-medium transition-colors hover:text-foreground data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm"
				>
					Waveforms
				</Tabs.Trigger>
				<Tabs.Trigger
					value="properties"
					class="inline-flex items-center justify-center rounded-sm px-2.5 py-1 text-[0.65rem] font-medium transition-colors hover:text-foreground data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm"
				>
					Properties
				</Tabs.Trigger>
			</Tabs.List>
			<Tabs.Content value="waveforms" class="mt-3">
				<ProfileWaveforms {session} {profileId} />
			</Tabs.Content>
			<Tabs.Content value="properties" class="mt-3">
				<ProfileProperties {session} {profileId} />
			</Tabs.Content>
		</Tabs.Root>
	</section>
{/if}
