<script lang="ts">
	import type { Session } from '$lib/main';
	import { sanitizeString, cn } from '$lib/utils';
	import { selectVariants } from '$lib/ui/kit/Select.svelte';
	import { ChevronUpDown, DotsSpinner, Check, LockOutline, LockOpenOutline } from '$lib/icons';
	import { Dialog } from '$lib/ui/kit';
	import { Select } from 'bits-ui';
	import { watch } from 'runed';

	interface Props {
		session: Session;
		selected?: string;
		switchOnChange?: boolean;
		size?: 'xs' | 'sm' | 'md' | 'lg';
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
	const selectedHasStacks = $derived(session.stacks.some((s) => s.profile_id === selected));
	const loading = $derived(switchOnChange ? session.isSwitchingProfile : false);
	const styles = $derived(selectVariants({ variant: 'filled', size }));

	const iconSize = $derived({ xs: 10, sm: 12, md: 14, lg: 16 }[size]);

	let lockDialogOpen = $state(false);

	function handleChange(value: string | undefined) {
		if (!value) return;
		selected = value;
		if (switchOnChange) {
			session.activateProfile(value);
		}
	}

	function handleLockClick(e: MouseEvent) {
		e.stopPropagation();
		if (session.gridForceUnlocked) {
			session.gridForceUnlocked = false;
		} else {
			lockDialogOpen = true;
		}
	}
</script>

<Select.Root type="single" value={selected} onValueChange={handleChange} {items} disabled={loading}>
	<div class="relative">
		<Select.Trigger class={cn(styles.trigger(), 'rounded-md pr-8', className)}>
			<span class="truncate">
				{#if selectedLabel}
					{selectedLabel}
				{:else}
					<span class="text-fg-muted">Select profile...</span>
				{/if}
			</span>
		</Select.Trigger>
		<div class="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2">
			{#if loading}
				<DotsSpinner class="text-fg-muted" width={iconSize} height={iconSize} />
			{:else if selectedHasStacks}
				<button
					class="pointer-events-auto cursor-pointer rounded p-0.5 transition-colors
						{session.gridForceUnlocked ? 'text-danger hover:text-danger/80' : 'text-info hover:text-fg'}"
					title={session.gridForceUnlocked ? 'Re-lock grid' : 'Unlock grid editing'}
					onclick={handleLockClick}
				>
					{#if session.gridForceUnlocked}
						<LockOpenOutline width={iconSize} height={iconSize} />
					{:else}
						<LockOutline width={iconSize} height={iconSize} />
					{/if}
				</button>
			{:else}
				<ChevronUpDown class="opacity-50" width={iconSize} height={iconSize} />
			{/if}
		</div>
	</div>

	<Select.Portal>
		<Select.Content align="start" class={styles.content()}>
			{#if profiles.length === 0}
				<div class="px-3 py-2 text-base text-fg-muted">No profiles available</div>
			{:else}
				<Select.Viewport class="max-h-(--bits-select-content-available-height) overflow-y-auto">
					<Select.Group>
						{#each profiles as profile (profile.value)}
							{@const hasStacks = session.stacks.some((s) => s.profile_id === profile.value)}
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
										<span class="text-xs text-fg-muted">{profile.description}</span>
									{/if}
								</div>
								{#if hasStacks}
									<span class="mt-0.5 inline-block size-1.5 shrink-0 rounded-full bg-info"> </span>
								{/if}
							</Select.Item>
						{/each}
					</Select.Group>
				</Select.Viewport>
			{/if}
		</Select.Content>
	</Select.Portal>
</Select.Root>

<Dialog.Root bind:open={lockDialogOpen}>
	<Dialog.Portal>
		<Dialog.Overlay />
		<Dialog.Content>
			<Dialog.Header>
				<Dialog.Title>Unlock grid editing</Dialog.Title>
				<Dialog.Description>
					Stacks exist for this profile. Changing grid offset or overlap will recalculate stack positions. Continue?
				</Dialog.Description>
			</Dialog.Header>
			<Dialog.Footer>
				<button
					onclick={() => (lockDialogOpen = false)}
					class="rounded border border-border px-3 py-1.5 text-sm text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
				>
					Cancel
				</button>
				<button
					onclick={() => {
						session.gridForceUnlocked = true;
						lockDialogOpen = false;
					}}
					class="rounded bg-danger px-3 py-1.5 text-sm text-danger-fg transition-colors hover:bg-danger/90"
				>
					Unlock
				</button>
			</Dialog.Footer>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
