<script lang="ts">
	import type { Session } from '$lib/main';
	import StagePosition from './StagePosition.svelte';
	import { offsetControl, overlapControl, zDefaults } from './helpers.svelte';
	import XYPlane from './XYPlane.svelte';
	import ZPlane from './ZPlane.svelte';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();
</script>

{#if session.stage && session.stage.x && session.stage.y && session.stage.z}
	{@const gc = session.config.profiles[session.activeProfileId ?? '']?.grid ?? null}
	<div class="grid h-full grid-rows-[auto_1fr_auto] gap-6">
		{#if gc}
			<div class="flex w-full flex-wrap items-center justify-between gap-4 p-4">
				{@render offsetControl(session, gc)}
				{@render overlapControl(session, gc)}
			</div>
		{/if}
		<div class="flex min-h-0 min-w-0 items-stretch gap-4 px-4">
			<XYPlane {session} />
			<ZPlane {session} />
		</div>
		{#if gc}
			<div class="flex h-ui-xl w-full flex-wrap items-center justify-between gap-4 border-t border-border px-4">
				<StagePosition stage={session.stage} />
				{@render zDefaults(session, gc)}
			</div>
		{/if}
	</div>
{:else}
	<div class="grid h-full w-full place-content-center">
		<p class="text-base text-fg-muted">Stage not available</p>
	</div>
{/if}
