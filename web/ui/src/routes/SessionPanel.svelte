<script lang="ts">
	import type { Session } from '$lib/main';
	import { sanitizeString } from '$lib/utils';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	const activeProfileLabel = $derived(
		(() => {
			const p = session.activeProfileConfig;
			return p ? (p.label ?? p.desc ?? sanitizeString(session.activeProfileId ?? '')) : 'No profile';
		})()
	);
</script>

<div class="h-full overflow-auto bg-card p-4">
	<div class="space-y-4 text-sm text-muted-foreground">
		<h3 class="text-xs font-medium uppercase">Session Info</h3>
		<div class="grid grid-cols-2 gap-2 text-xs">
			<span>Config</span>
			<span class="text-foreground">{session.config.info.name}</span>
			<span>Active profile</span>
			<span class="text-foreground">{activeProfileLabel}</span>
			<span>Tiles</span>
			<span class="text-foreground">{session.tiles.length}</span>
			<span>Stacks</span>
			<span class="text-foreground">{session.stacks.length}</span>
			<span>Stage connected</span>
			<span class="text-foreground">{session.stage.connected ? 'Yes' : 'No'}</span>
		</div>

		<h3 class="text-xs font-medium uppercase">Stage</h3>
		<div class="grid grid-cols-2 gap-2 text-xs">
			<span>X position</span>
			<span class="text-foreground">{session.stage.x.position.toFixed(3)} mm</span>
			<span>Y position</span>
			<span class="text-foreground">{session.stage.y.position.toFixed(3)} mm</span>
			<span>Z position</span>
			<span class="text-foreground">{session.stage.z.position.toFixed(3)} mm</span>
			<span>Moving</span>
			<span class="text-foreground">{session.stage.isMoving ? 'Yes' : 'No'}</span>
		</div>

		<h3 class="text-xs font-medium uppercase">Grid</h3>
		<div class="grid grid-cols-2 gap-2 text-xs">
			<span>Overlap</span>
			<span class="text-foreground">{(session.gridConfig.overlap * 100).toFixed(0)}%</span>
			<span>Tile order</span>
			<span class="text-foreground">{session.tileOrder}</span>
			<span>Grid locked</span>
			<span class="text-foreground">{session.gridLocked ? 'Yes' : 'No'}</span>
			<span>FOV</span>
			<span class="text-foreground">{session.fov.width.toFixed(2)} x {session.fov.height.toFixed(2)} mm</span>
		</div>
	</div>
</div>
