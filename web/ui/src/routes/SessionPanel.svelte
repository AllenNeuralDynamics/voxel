<script lang="ts">
	import type { Session } from '$lib/main';
	import { Logout } from '$lib/icons';
	import { sanitizeString } from '$lib/utils';

	interface Props {
		session: Session;
		onExit?: () => void;
	}

	let { session, onExit }: Props = $props();

	const activeProfileLabel = $derived.by(() => {
		const id = session.activeProfileId;
		const p = id ? (session.config.profiles[id] ?? null) : null;
		return p ? (p.label ?? sanitizeString(id ?? '')) : '—';
	});

	const deviceCount = $derived(session.devices.devices.size);
	const connectedCount = $derived([...session.devices.devices.values()].filter((d) => d.connected).length);

	/** Truncate directory path to last N segments. */
	function shortenPath(path: string, segments = 3): string {
		const parts = path.split('/').filter(Boolean);
		if (parts.length <= segments) return path;
		return '.../' + parts.slice(-segments).join('/');
	}
</script>

<div class="flex h-full flex-col justify-between bg-card px-4 py-3 text-xs">
	<div class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
		<span class="text-muted-foreground">Rig</span>
		<span class="text-foreground">{session.config.info.name}</span>

		<span class="text-muted-foreground">Profile</span>
		<span class="text-foreground">{activeProfileLabel}</span>

		<span class="text-muted-foreground">Devices</span>
		<span class="text-foreground">{connectedCount}/{deviceCount}</span>

		<span class="text-muted-foreground">Tiles</span>
		<span class="text-foreground">{session.tiles.length}</span>

		<span class="text-muted-foreground">Stacks</span>
		<span class="text-foreground">{session.stacks.length}</span>

		{#if session.sessionDir}
			<span class="text-muted-foreground">Directory</span>
			<span class="truncate text-foreground" title={session.sessionDir}>
				{shortenPath(session.sessionDir)}
			</span>
		{/if}
	</div>

	<div class="flex justify-end">
		<button
			onclick={() => onExit?.()}
			class="flex cursor-pointer items-center gap-1 text-muted-foreground transition-colors hover:text-foreground"
			aria-label="Close Session"
			title="Close Session"
		>
			Exit <Logout width="11" height="11" />
		</button>
	</div>
</div>
