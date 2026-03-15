<script lang="ts">
	import type { Session } from '$lib/main';
	import { sanitizeString, cn } from '$lib/utils';
	import { selectVariants, type SelectVariants } from '$lib/ui/kit/Select.svelte';
	import { ChevronUpDown, DotsSpinner, Check } from '$lib/icons';
	import { Select } from 'bits-ui';
	import { watch } from 'runed';

	interface Props {
		session: Session;
		selected?: string;
		switchOnChange?: boolean;
		size?: SelectVariants['size'];
		class?: string;
	}

	let {
		session,
		selected = $bindable(session.activeProfileId ?? ''),
		switchOnChange = true,
		size = 'md',
		class: className
	}: Props = $props();

	watch(
		() => session.activeProfileId,
		(id) => {
			if (id) selected = id;
		}
	);

	const profiles = $derived(
		Object.entries(session.config.profiles).map(([id, cfg]) => ({
			value: id,
			label: cfg.label ?? sanitizeString(id),
			description: cfg.desc
		}))
	);

	const items = $derived(profiles.map((p) => ({ value: p.value, label: p.label })));
	const selectedLabel = $derived(profiles.find((p) => p.value === selected)?.label ?? '');
	const selectedStatus = $derived(profileStatus(selected));
	const loading = $derived(switchOnChange ? session.isSwitchingProfile : false);
	const styles = $derived(selectVariants({ variant: 'filled', size }));

	const iconSizes: Record<NonNullable<SelectVariants['size']>, number> = {
		xs: 10,
		sm: 12,
		md: 14,
		lg: 16
	};

	function profileStatus(id: string): 'stacks' | 'in-plan' | null {
		if (session.stacks.some((s) => s.profile_id === id)) return 'stacks';
		if (id in session.plan.grid_configs) return 'in-plan';
		return null;
	}

	function handleChange(value: string | undefined) {
		if (!value) return;
		selected = value;
		if (switchOnChange) {
			session.activateProfile(value);
		}
	}
</script>

<Select.Root type="single" value={selected} onValueChange={handleChange} {items} disabled={loading}>
	<Select.Trigger class={cn(styles.trigger(), className)}>
		<span class="flex items-center gap-1.5 truncate">
			{#if selectedLabel}
				{selectedLabel}
			{:else}
				<span class="text-fg-muted">Select profile...</span>
			{/if}
			{#if selectedStatus}
				<span
					class="inline-block size-1.5 shrink-0 rounded-full {selectedStatus === 'stacks' ? 'bg-info' : 'bg-warning'}"
				></span>
			{/if}
		</span>
		{#if loading}
			<DotsSpinner class="text-fg-muted shrink-0" width={iconSizes[size]} height={iconSizes[size]} />
		{:else}
			<ChevronUpDown class="shrink-0 opacity-50" width={iconSizes[size]} height={iconSizes[size]} />
		{/if}
	</Select.Trigger>

	<Select.Portal>
		<Select.Content align="start" class={styles.content()}>
			{#if profiles.length === 0}
				<div class="text-fg-muted px-3 py-2 text-base">No profiles available</div>
			{:else}
				<Select.Viewport class="max-h-(--bits-select-content-available-height) overflow-y-auto">
					<Select.Group>
						{#each profiles as profile (profile.value)}
							{@const status = profileStatus(profile.value)}
							<Select.Item
								value={profile.value}
								label={profile.label}
								class={cn(styles.item(), profile.description ? 'items-start' : 'items-center')}
							>
								<span class="inline-flex h-3 w-3 shrink-0 items-center justify-center text-primary">
									{#if selected === profile.value}
										<Check class="h-3 w-3" />
									{/if}
								</span>
								<div class="flex min-w-0 flex-1 flex-col gap-0.5">
									<span class="text-fg">{profile.label}</span>
									{#if profile.description}
										<span class="text-fg-muted text-xs">{profile.description}</span>
									{/if}
								</div>
								{#if status}
									<span
										class="mt-0.5 inline-block size-1.5 shrink-0 rounded-full {status === 'stacks'
											? 'bg-info'
											: 'bg-warning'}"
									></span>
								{/if}
							</Select.Item>
						{/each}
					</Select.Group>
				</Select.Viewport>
			{/if}
		</Select.Content>
	</Select.Portal>
</Select.Root>
