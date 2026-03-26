<script lang="ts">
	import { page } from '$app/state';
	import { sanitizeString } from '$lib/utils';

	const stepId = $derived(page.params.step!);
	const stepLabel = $derived(sanitizeString(stepId));
</script>

<div class="flex h-full items-center justify-center">
	<p class="text-base text-fg-muted">{stepLabel} — coming soon</p>
</div>
