<script lang="ts">
	import { page } from '$app/state';
	import { getSessionContext } from '$lib/context';
	import { sanitizeString } from '$lib/utils';

	const session = getSessionContext();
	const stepId = $derived(page.params.step!);
	const stepLabel = $derived(
		session.workflow.steps.find((s) => s.id === stepId)?.label ?? sanitizeString(stepId)
	);
</script>

<div class="flex h-full items-center justify-center">
	<p class="text-sm text-muted-foreground">{stepLabel} — coming soon</p>
</div>
