<script lang="ts">
	import type { Snippet } from 'svelte';

	const {
		label,
		id,
		children
	}: {
		label: string;
		id?: string;
		children: Snippet;
	} = $props();
</script>

<div class="grid gap-1">
	<label for={id} class="text-[0.65rem] text-muted-foreground/70">
		{label}
	</label>
	{@render children()}
</div>
