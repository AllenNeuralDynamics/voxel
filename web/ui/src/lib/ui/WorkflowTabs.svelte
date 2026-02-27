<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const workflowTabsVariants = tv({
		base: 'flex items-center gap-1.5'
	});

	export type WorkflowTabsVariants = VariantProps<typeof workflowTabsVariants>;

	const tabVariants = tv({
		base: 'flex items-center gap-1 px-3 py-1.5 text-[0.65rem] uppercase tracking-wide transition-all text-muted-foreground rounded-xl border border-border',
		variants: {
			viewing: {
				true: 'bg-muted font-medium text-foreground',
				false: ''
			},
			state: {
				committed: '',
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
	import { ChevronLeft, Check, ChevronRight } from '$lib/icons';
	import { cn } from '$lib/utils';
	import type { Workflow } from '$lib/main';

	interface Props {
		workflow: Workflow;
		viewId: string;
		class?: string;
	}

	let { workflow, viewId = $bindable(), class: className }: Props = $props();

	function handleBack() {
		const stepId = workflow.back();
		if (stepId) viewId = stepId;
	}

	function handleNext() {
		const stepId = workflow.next();
		viewId = stepId ?? 'acquire';
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
					'cursor-pointer overflow-hidden transition-all  duration-200',
					isActive ? 'w-3.5' : 'w-0',
					isActive && workflow.canGoBack ? 'opacity-100' : 'pointer-events-none cursor-not-allowed opacity-40'
				)}
				title="Re-open previous step"
			>
				<ChevronLeft width="14" height="14" />
			</button>
			<button
				onclick={() => (viewId = step.id)}
				class="flex w-20 cursor-pointer items-center justify-center gap-2 uppercase"
			>
				<span
					class={cn(
						'flex h-3 w-3 items-center justify-center rounded-full border transition-colors',
						state === 'committed'
							? 'border-success bg-success text-white'
							: state === 'active'
								? 'border-success'
								: 'border-muted-foreground/30'
					)}
				>
					{#if state === 'committed'}
						<Check width="8" height="8" class="pointer-events-none" />
					{/if}
				</span>
				{step.label}
			</button>
			<button
				disabled={!workflow.canAdvance}
				onclick={handleNext}
				class={cn(
					'cursor-pointer overflow-hidden transition-all  duration-200',
					isActive ? 'w-3.5' : 'w-0',
					isActive && workflow.canAdvance ? 'opacity-100' : 'pointer-events-none cursor-not-allowed opacity-40'
				)}
				title="Commit step and advance"
			>
				<ChevronRight width="14" height="14" />
			</button>
		</div>
	{/each}
</div>
