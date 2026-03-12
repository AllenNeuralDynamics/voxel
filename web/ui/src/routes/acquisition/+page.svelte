<script lang="ts">
	import { getSessionContext } from '$lib/context';
	import MetadataPanel from '$lib/ui/MetadataPanel.svelte';

	const session = getSessionContext();
	// const workflow = $derived(session.workflow);
	const stackSummary = $derived.by(() => {
		const total = session.stacks.length;
		const completed = session.stacks.filter((s) => s.status === 'completed').length;
		const profiles = Object.keys(session.plan.grid_configs).length;
		return { total, completed, profiles };
	});
</script>

<div class="flex h-full flex-col">
	<div class="flex-1 overflow-y-auto px-4 pt-4">
		<!-- Side-by-side on wide, stacked on narrow -->
		<div class="flex flex-col gap-6 lg:flex-row">
			<!-- Metadata -->
			<div class="min-w-0 flex-1">
				<MetadataPanel {session} />
			</div>

			<!-- Acquisition plan -->
			<div class="min-w-0 flex-1">
				<h3 class="mb-2 text-[0.65rem] font-medium tracking-wide text-muted-foreground/70 uppercase">Plan</h3>
				<div class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
					<span class="text-muted-foreground">Stacks</span>
					<span class="text-foreground">
						{stackSummary.completed}/{stackSummary.total}
					</span>

					<span class="text-muted-foreground">Profiles</span>
					<span class="text-foreground">{stackSummary.profiles}</span>

					<span class="text-muted-foreground">Mode</span>
					<span class="text-foreground">{session.mode}</span>
				</div>
			</div>
		</div>
	</div>
</div>
