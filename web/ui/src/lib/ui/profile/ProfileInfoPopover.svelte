<script lang="ts">
	import type { Session } from '$lib/main';
	import { Popover } from 'bits-ui';
	import { InformationOutline } from '$lib/icons';
	import { sanitizeString } from '$lib/utils';

	type Size = 'sm' | 'md' | 'lg';

	interface Props {
		session: Session;
		profileId: string;
		size?: Size;
	}

	let { session, profileId, size = 'sm' }: Props = $props();

	const iconSize: Record<Size, string> = {
		sm: '16',
		md: '18',
		lg: '20'
	};

	const config = $derived(session.config);
	const profile = $derived(config.profiles[profileId]);
</script>

{#if profile && (profile.desc || profile.channels.length > 0)}
	<Popover.Root>
		<Popover.Trigger
			class="text-fg-muted hover:bg-element-hover hover:text-fg rounded-lg px-1 py-0.5 transition-colors"
		>
			<InformationOutline width={iconSize[size]} height={iconSize[size]} />
		</Popover.Trigger>
		<Popover.Portal>
			<Popover.Content
				class="bg-floating text-fg z-50 w-72 rounded-xl border border-border p-4 shadow-md"
				side="bottom"
				align="end"
				sideOffset={6}
			>
				{#if profile.desc}
					<p class="text-xs">{profile.desc}</p>
				{/if}
				{#if profile.channels.length > 0}
					<p class="text-xs {profile.desc ? 'mt-1.5' : ''} text-fg-muted">
						{#each profile.channels as chId, i (chId)}{#if i > 0},
							{/if}{config.channels[chId]?.label ?? sanitizeString(chId)}{/each}
					</p>
				{/if}
			</Popover.Content>
		</Popover.Portal>
	</Popover.Root>
{/if}
