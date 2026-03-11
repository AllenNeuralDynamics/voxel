<script lang="ts">
	import { goto } from '$app/navigation';
	import { getAppContext } from '$lib/context';
	import { Button } from '$lib/ui/kit';
	import { ChevronLeft } from '$lib/icons';
	import { resolve } from '$app/paths';

	const app = getAppContext();
	const session = $derived(app.session!);
	const workflow = $derived(session.workflow);
</script>

{#if workflow.allCommitted}
	<div class="flex h-full flex-col justify-between">
		<div class="flex h-full items-center justify-between px-4">
			<p class="w-full text-center text-sm text-muted-foreground">Coming soon</p>
		</div>
		<div class="px-4 py-3">
			<Button
				variant="ghost"
				size="xs"
				onclick={() => {
					const stepId = workflow.back();
					if (stepId) goto(resolve(`/workflow/${stepId}`), { keepFocus: true, noScroll: true });
				}}
			>
				<ChevronLeft width="12" height="12" /> Back to setup
			</Button>
		</div>
	</div>
{:else}
	<div class="flex h-full items-center justify-center">
		<p class="text-sm text-muted-foreground">Complete all workflow steps before acquiring</p>
	</div>
{/if}
