<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const workflowTabsVariants = tv({
		base: 'flex items-center [&>*:not(:first-child)]:-ml-px'
	});

	export type WorkflowTabsVariants = VariantProps<typeof workflowTabsVariants>;

	const tabVariants = tv({
		base: 'flex items-center gap-1 text-[0.65rem] uppercase tracking-wide transition-all text-muted-foreground rounded-none border border-border',
		variants: {
			viewing: {
				true: 'bg-muted',
				false: ''
			},
			state: {
				committed: 'text-success',
				active: '',
				pending: ''
			}
		},
		defaultVariants: {
			viewing: false,
			state: 'pending'
		}
	});
</script>

<script lang="ts">
	import { ChevronLeft, ChevronRight } from '$lib/icons';
	import { cn } from '$lib/utils';
	import type { Workflow } from '$lib/main';

	interface Props {
		workflow: Workflow;
		viewId: string;
		onViewChange?: (id: string) => void;
		class?: string;
	}

	let { workflow, viewId, onViewChange, class: className }: Props = $props();

	function handleBack() {
		const stepId = workflow.back();
		if (stepId) onViewChange?.(stepId);
	}

	function handleNext() {
		const stepId = workflow.next();
		onViewChange?.(stepId ?? 'acquire');
	}
</script>

<div class={cn(workflowTabsVariants(), className)}>
	{#each workflow.steps as step (step.id)}
		{@const state = workflow.stepStates[step.id]}
		{@const isActive = state === 'active'}
		<div class={cn(tabVariants({ viewing: viewId === step.id, state }), 'justify-between hover:text-foreground')}>
			<button
				disabled={!workflow.canGoBack}
				onclick={handleBack}
				class={cn(
					'grid h-6 cursor-pointer place-content-center overflow-hidden py-1.5 transition-all duration-200',
					isActive ? 'w-6' : 'w-0',
					isActive && workflow.canGoBack ? 'opacity-100' : 'pointer-events-none cursor-not-allowed opacity-40'
				)}
				title="Re-open previous step"
			>
				<ChevronLeft width="14" height="14" />
			</button>
			<button
				onclick={() => onViewChange?.(step.id)}
				class="flex w-20 cursor-pointer items-center justify-center p-1.5 uppercase"
			>
				{step.label}
			</button>
			<button
				disabled={!workflow.canAdvance}
				onclick={handleNext}
				class={cn(
					'grid h-6 cursor-pointer place-content-center overflow-hidden py-1.5 transition-all duration-200',
					isActive ? 'w-6' : 'w-0',
					isActive && workflow.canAdvance ? 'opacity-100' : 'pointer-events-none cursor-not-allowed opacity-40'
				)}
				title="Commit step and advance"
			>
				<ChevronRight width="14" height="14" />
			</button>
		</div>
	{/each}
</div>
