<script lang="ts">
	import type { Session } from '$lib/main';
	import { createGridLock, offsetControl, overlapControl, zDefaults, lockIndicator } from './helpers.svelte';
	import XYPlane from './XYPlane.svelte';
	import ZPlane from './ZPlane.svelte';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	const lock = createGridLock(() => session);
</script>

{#if session.stage.x && session.stage.y && session.stage.z}
	{@const gc = session.config.profiles[session.activeProfileId ?? '']?.grid ?? null}
	<div class="grid h-full grid-rows-[auto_1fr_auto] gap-6 p-4">
		{#if gc}
			<div class="flex w-full flex-wrap items-center justify-between gap-4">
				{@render offsetControl(session, lock, gc)}
				{@render overlapControl(session, lock, gc)}
			</div>
		{/if}
		<div class="flex min-h-0 w-full items-stretch gap-4">
			<XYPlane {session} />
			<ZPlane {session} />
		</div>
		{#if gc}
			<div class="flex w-full flex-wrap items-center justify-between gap-4">
				{@render zDefaults(session, gc)}
				{@render lockIndicator(session, lock)}
			</div>
		{/if}
	</div>
{:else}
	<div class="grid h-full w-full place-content-center">
		<p class="text-fg-muted text-base">Stage not available</p>
	</div>
{/if}
