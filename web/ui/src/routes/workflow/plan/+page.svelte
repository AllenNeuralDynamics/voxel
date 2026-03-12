<script lang="ts">
	import { getSessionContext } from '$lib/context';

	const session = getSessionContext();
</script>

<div class="flex h-full flex-col items-center justify-center gap-2">
	<p class="text-sm text-muted-foreground">Plan — define stacks for acquisition</p>
	<p class="text-xs text-muted-foreground">
		{session.tiles.length} tiles · {session.stacks.length} stacks
	</p>
</div>
