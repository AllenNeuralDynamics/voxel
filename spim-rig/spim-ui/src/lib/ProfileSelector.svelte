<script lang="ts">
	import Icon from '@iconify/svelte';
	import { Select as SelectPrimitive } from 'bits-ui';
	import { sanitizeString } from '$lib/utils';
	import type { Profile, ProfilesManager } from '$lib/profiles.svelte';

	const { manager } = $props<{ manager: ProfilesManager }>();

	const selectedProfile = $derived(
		manager.profiles.find((profile: Profile) => profile.id === manager.activeProfileId) ?? null
	);
	const selectItems = $derived(
		manager.profiles.map((profile: Profile) => ({
			value: profile.id,
			label: profile.label ?? profile.desc ?? sanitizeString(profile.id)
		}))
	);
	const selectedValue = $derived(selectedProfile ? selectedProfile.id : '');
	const isDisabled = $derived(manager.isLoading || manager.isMutating || manager.profiles.length === 0);
	const placeholderText = $derived(manager.isLoading ? 'Loading profiles...' : 'Select a profile');

	function formatProfileName(profile: Profile | null) {
		if (!profile) return '';
		return profile.label ?? sanitizeString(profile.id);
	}

	function handleChange(value: string) {
		if (!value) return;
		if (value === manager.activeProfileId) return;
		if (manager.isMutating) return;

		void manager.activateProfile(value);
	}
</script>

<div class="flex flex-col gap-1">
	<div class="flex items-center gap-1.5">
		<SelectPrimitive.Root
			type="single"
			value={selectedValue}
			onValueChange={handleChange}
			items={selectItems}
			disabled={isDisabled}
		>
			<SelectPrimitive.Trigger
				class="group flex h-10 w-full items-center justify-between rounded border border-zinc-500/80 bg-zinc-900/70 px-3 text-sm text-zinc-200 shadow-sm transition hover:border-zinc-600 focus-visible:ring-2 focus-visible:ring-zinc-600 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
			>
				<span class="truncate text-left">
					{#if selectedProfile}
						{formatProfileName(selectedProfile)}
					{:else}
						<span class="text-zinc-500">{placeholderText}</span>
					{/if}
				</span>

				{#if manager.isMutating}
					<Icon icon="svg-spinners:3-dots-fade" class="text-zinc-400" width="16" height="16" />
				{:else}
					<Icon icon="mdi:chevron-up-down" class="text-zinc-400 group-hover:text-zinc-200" width="20" height="20" />
				{/if}
			</SelectPrimitive.Trigger>

			<SelectPrimitive.Content
				align="start"
				class="relative z-50 mt-1 w-(--bits-select-anchor-width) min-w-(--bits-select-anchor-width) rounded border border-zinc-700 bg-zinc-950/95 p-1.5 text-zinc-50 shadow-xl"
			>
				{#if manager.profiles.length === 0 && !manager.isLoading}
					<div class="px-3 py-2 text-sm text-zinc-500">No profiles available</div>
				{:else}
					<div class="max-h-56 overflow-y-auto">
						<SelectPrimitive.Group>
							{#each manager.profiles as profile (profile.id)}
								<SelectPrimitive.Item
									value={profile.id}
									label={profile.desc}
									class="relative flex w-full cursor-default items-start gap-2 rounded-md px-3 py-2 text-sm outline-none select-none data-disabled:pointer-events-none data-disabled:opacity-40 data-highlighted:bg-zinc-800"
								>
									<span class="inline-flex h-4 w-4 items-center justify-center text-xs text-emerald-400">
										{#if manager.activeProfileId === profile.id}
											<Icon icon="material-symbols:check-small-rounded" class="h-4 w-4" />
										{/if}
									</span>
									<div class="flex flex-col">
										<p class="text-sm font-medium text-zinc-100">{formatProfileName(profile)}</p>
										<p class="text-[0.7rem] text-zinc-300">{profile.desc}</p>
									</div>
								</SelectPrimitive.Item>
							{/each}
						</SelectPrimitive.Group>
					</div>
				{/if}
			</SelectPrimitive.Content>
		</SelectPrimitive.Root>
	</div>

	{#if manager.error}
		<p class="text-xs text-rose-400">{manager.error}</p>
	{/if}
</div>
