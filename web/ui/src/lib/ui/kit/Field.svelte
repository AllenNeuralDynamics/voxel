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
	<label for={id} class="text-fg-muted text-xs">
		{label}
	</label>
	{@render children()}
</div>
