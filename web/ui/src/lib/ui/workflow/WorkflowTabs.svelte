<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const workflowTabsVariants = tv({
		base: 'flex items-center rounded-lg border border-border'
	});

	export type WorkflowTabsVariants = VariantProps<typeof workflowTabsVariants>;

	const tabVariants = tv({
		base: 'flex flex-1 items-center gap-2 px-3 py-1.5 text-xs uppercase tracking-wide transition-colors',
		variants: {
			state: {
				viewing: 'bg-muted text-foreground font-medium',
				current: 'text-foreground',
				default: 'text-muted-foreground'
			}
		},
		defaultVariants: {
			state: 'default'
		}
	});
</script>

<script lang="ts">
	import Icon from '@iconify/svelte';
	import { cn } from '$lib/utils';
	import type { WorkflowStepConfig } from '$lib/main/types';
	import type { Workflow } from './workflow.svelte';

	interface Props {
		workflow: Workflow;
		onnavigate?: () => void;
		class?: string;
	}

	let { workflow, onnavigate, class: className }: Props = $props();

	function handleView(stepId: string) {
		workflow.view(stepId);
		onnavigate?.();
	}

	function handleReopen(stepId: string) {
		workflow.reopen(stepId);
		onnavigate?.();
	}

	function handleNext() {
		workflow.next();
		onnavigate?.();
	}

	function tabState(step: WorkflowStepConfig): 'viewing' | 'current' | 'default' {
		if (workflow.isViewing(step.id)) return 'viewing';
		if (workflow.isCurrent(step.id)) return 'current';
		return 'default';
	}
</script>

<div class={cn(workflowTabsVariants(), className)}>
	{#each workflow.visibleSteps as step (step.id)}
		<div class={tabVariants({ state: tabState(step) })}>
			{#if step.state === 'completed' && !workflow.isViewing(step.id)}
				<button
					onclick={() => handleReopen(step.id)}
					class="flex h-3 w-3 cursor-pointer items-center justify-center rounded-full border border-success bg-success text-white transition-colors hover:border-destructive hover:bg-destructive"
					title="Re-open step"
				>
					<Icon icon="mdi:check" width="8" height="8" class="pointer-events-none" />
				</button>
			{:else}
				<span
					class={cn(
						'flex h-3 w-3 items-center justify-center rounded-full border transition-colors',
						step.state === 'completed'
							? 'border-success bg-success text-white'
							: workflow.isCurrent(step.id)
								? 'border-foreground/50'
								: 'border-muted-foreground/30'
					)}
				>
					{#if step.state === 'completed'}
						<Icon icon="mdi:check" width="8" height="8" class="pointer-events-none" />
					{/if}
				</span>
			{/if}
			<button onclick={() => handleView(step.id)} class="cursor-pointer hover:text-foreground">
				{step.label}
			</button>
		</div>
	{/each}
	<button
		disabled={!workflow.canAdvance}
		onclick={handleNext}
		class={cn(
			'flex items-center justify-center border-l border-border px-2 py-1.5 text-muted-foreground transition-colors',
			!workflow.canAdvance ? 'cursor-not-allowed opacity-40' : 'hover:bg-muted hover:text-foreground'
		)}
		title="Next step"
	>
		<Icon icon="mdi:chevron-right" width="14" height="14" />
	</button>
</div>
