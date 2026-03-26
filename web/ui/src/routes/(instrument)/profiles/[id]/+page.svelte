<script lang="ts">
	import { getSessionContext } from '$lib/context';
	import { page } from '$app/state';
	import { sanitizeString } from '$lib/utils';
	import ProfileWaveforms from './ProfileWaveforms.svelte';
	import CamerasPanel from '$lib/ui/CamerasPanel.svelte';
	import AuxDevicesPanel from '$lib/ui/AuxDevicesPanel.svelte';
	import LasersPanel from '$lib/ui/LasersPanel.svelte';

	const session = getSessionContext();
	const profileId = $derived(page.params.id!);
	const profile = $derived(session.config.profiles[profileId]);
</script>

{#if profile}
	{@const sectionHeader = 'text-xs font-medium tracking-wide text-fg-muted uppercase mb-2'}
	<section class="flex h-full flex-col gap-2">
		<!-- Header -->
		<div class="px-4">
			<div class="flex items-center gap-1.5">
				<h2 class="text-base font-medium text-fg">
					{profile.label ?? sanitizeString(profileId)}
				</h2>
				<div class="ml-auto flex items-center gap-1.5">
					{#each profile.channels as chId (chId)}
						<span class="rounded-full bg-element-bg px-1.5 py-px text-xs text-fg">
							{session.config.channels[chId]?.label ?? sanitizeString(chId)}
						</span>
					{/each}
				</div>
			</div>
			{#if profile.desc}
				<p class="mt-1 text-sm text-fg-muted">{profile.desc}</p>
			{/if}
		</div>
		<div class="space-y-4 overflow-auto p-4">
			<section>
				<h3 class={sectionHeader}>Waveforms</h3>
				<ProfileWaveforms {session} {profileId} />
			</section>
			<section>
				<h3 class={sectionHeader}>Lasers</h3>
				<LasersPanel {session} {profileId} class="rounded border border-border" />
			</section>
			<section>
				<h3 class={sectionHeader}>Cameras</h3>
				<CamerasPanel {session} {profileId} panelSide="left" class="rounded border border-border" />
			</section>
			<section>
				<h3 class={sectionHeader}>Auxilliary Devices</h3>
				<AuxDevicesPanel {session} {profileId} />
			</section>
		</div>
	</section>
{/if}
