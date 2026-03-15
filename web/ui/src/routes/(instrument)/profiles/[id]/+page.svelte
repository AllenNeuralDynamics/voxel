<script lang="ts">
	import { Tabs } from 'bits-ui';
	import { getSessionContext } from '$lib/context';
	import { page } from '$app/state';
	import { sanitizeString } from '$lib/utils';
	import ProfileProperties from './ProfileProperties.svelte';
	import ProfileWaveforms from './ProfileWaveforms.svelte';

	const session = getSessionContext();
	const profileId = $derived(page.params.id!);
	const profile = $derived(session.config.profiles[profileId]);
	let activeTab = $state('waveforms');
</script>

{#if profile}
	<section class="space-y-4">
		<!-- Header -->
		<div>
			<div class="flex items-center gap-1.5">
				<h2 class="text-fg text-base font-medium">
					{profile.label ?? sanitizeString(profileId)}
				</h2>
				<div class="ml-auto flex items-center gap-1.5">
					{#each profile.channels as chId (chId)}
						<span class="bg-element-bg text-fg rounded-full px-1.5 py-px text-xs">
							{session.config.channels[chId]?.label ?? sanitizeString(chId)}
						</span>
					{/each}
				</div>
			</div>
			{#if profile.desc}
				<p class="text-fg-muted mt-1 text-sm">{profile.desc}</p>
			{/if}
		</div>

		<!-- Tabs -->
		<Tabs.Root bind:value={activeTab}>
			<Tabs.List class="bg-element-bg text-fg-muted inline-flex h-7 items-center gap-1 rounded-md p-0.5">
				<Tabs.Trigger
					value="waveforms"
					class="hover:text-fg data-[state=active]:bg-canvas data-[state=active]:text-fg inline-flex items-center justify-center rounded-sm px-2.5 py-1 text-xs font-medium transition-colors data-[state=active]:shadow-sm"
				>
					Waveforms
				</Tabs.Trigger>
				<Tabs.Trigger
					value="properties"
					class="hover:text-fg data-[state=active]:bg-canvas data-[state=active]:text-fg inline-flex items-center justify-center rounded-sm px-2.5 py-1 text-xs font-medium transition-colors data-[state=active]:shadow-sm"
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
