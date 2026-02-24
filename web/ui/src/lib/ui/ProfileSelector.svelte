<script lang="ts">
	import Icon from '@iconify/svelte';
	import { Select as SelectPrimitive } from 'bits-ui';
	import { sanitizeString } from '$lib/utils';
	import type { Session } from '$lib/main';

	const { session }: { session: Session } = $props();

	const profileEntries = $derived(Object.entries(session.config.profiles));
	const selectItems = $derived(
		profileEntries.map(([id, cfg]) => ({
			value: id,
			label: cfg.label ?? cfg.desc ?? sanitizeString(id)
		}))
	);
	const selectedValue = $derived(session.activeProfileId ?? '');
	const isDisabled = $derived(session.isMutating || profileEntries.length === 0);

	function formatProfileName(id: string) {
		const cfg = session.config.profiles[id];
		return cfg?.label ?? sanitizeString(id);
	}

	function handleChange(value: string) {
		if (!value) return;
		if (value === session.activeProfileId) return;
		if (session.isMutating) return;

		void session.activateProfile(value);
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
				class="group flex h-8 w-full min-w-72 items-center justify-between rounded border border-input bg-transparent px-3 text-sm transition-colors hover:border-foreground/20 focus:border-ring focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
			>
				<span class="truncate text-left">
					{#if session.activeProfileId}
						{formatProfileName(session.activeProfileId)}
					{:else}
						<span class="text-muted-foreground">Select a profile</span>
					{/if}
				</span>

				{#if session.isMutating}
					<Icon icon="svg-spinners:3-dots-fade" class="text-muted-foreground" width="16" height="16" />
				{:else}
					<Icon icon="mdi:chevron-up-down" class="shrink-0 opacity-50 group-hover:opacity-80" width="20" height="20" />
				{/if}
			</SelectPrimitive.Trigger>

			<SelectPrimitive.Portal>
				<SelectPrimitive.Content
					align="start"
					class="z-50 mt-1 w-(--bits-select-anchor-width) min-w-(--bits-select-anchor-width) origin-(--bits-select-content-transform-origin) rounded border bg-popover p-1.5 text-popover-foreground shadow-md data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95"
				>
					{#if profileEntries.length === 0}
						<div class="px-3 py-2 text-sm text-muted-foreground">No profiles available</div>
					{:else}
						<SelectPrimitive.Viewport class="max-h-144 overflow-y-auto">
							<SelectPrimitive.Group>
								{#each profileEntries as [profileId, profileConfig] (profileId)}
									<SelectPrimitive.Item
										value={profileId}
										label={profileConfig.desc}
										class="relative flex w-full cursor-default items-start gap-2 rounded-md px-3 py-2 text-sm outline-none select-none data-disabled:pointer-events-none data-disabled:opacity-40 data-highlighted:bg-accent data-highlighted:text-accent-foreground"
									>
										<span class="inline-flex h-4 w-4 items-center justify-center text-xs text-success">
											{#if session.activeProfileId === profileId}
												<Icon icon="material-symbols:check-small-rounded" class="h-4 w-4" />
											{/if}
										</span>
										<div class="flex flex-col">
											<p class="text-sm font-medium text-popover-foreground">{formatProfileName(profileId)}</p>
											<p class="text-[0.7rem] text-muted-foreground">{profileConfig.desc}</p>
										</div>
									</SelectPrimitive.Item>
								{/each}
							</SelectPrimitive.Group>
						</SelectPrimitive.Viewport>
					{/if}
				</SelectPrimitive.Content>
			</SelectPrimitive.Portal>
		</SelectPrimitive.Root>
	</div>

	{#if session.error}
		<p class="text-xs text-danger">{session.error}</p>
	{/if}
</div>
