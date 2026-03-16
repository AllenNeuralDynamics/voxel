<script lang="ts">
	import { getSessionContext } from '$lib/context';

	const session = getSessionContext();
</script>

<div class="flex h-full flex-col items-center justify-center gap-2">
	<p class="text-fg-muted text-base">Plan — define stacks for acquisition</p>
	<p class="text-fg-muted text-sm">
		{session.tiles.length} tiles · {session.stacks.length} stacks
	</p>
</div>
