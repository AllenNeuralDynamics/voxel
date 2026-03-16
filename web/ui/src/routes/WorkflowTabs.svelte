<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const workflowTabsVariants = tv({
		base: 'flex items-center [&>*:not(:first-child)]:-ml-px'
	});

	export type WorkflowTabsVariants = VariantProps<typeof workflowTabsVariants>;

	const tabVariants = tv({
		base: 'flex h-ui-lg items-center gap-1 text-xs uppercase tracking-wide transition-all text-fg-muted rounded-none border border-border first:rounded-l last:rounded-r',
		variants: {
			viewing: {
				true: 'bg-element-bg',
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
	import type { Session } from '$lib/main';

	interface Props {
		session: Session;
		viewId: string;
		onViewChange?: (id: string) => void;
		class?: string;
	}

	let { session, viewId, onViewChange, class: className }: Props = $props();

	const workflow = $derived(session.workflow);

	async function handleBack() {
		const stepId = await session.workflowBack();
		if (stepId) onViewChange?.(stepId);
	}

	async function handleNext() {
		const stepId = await session.workflowNext();
		onViewChange?.(stepId ?? 'acquisition');
	}
</script>

<div class={cn(workflowTabsVariants(), className)}>
	{#each workflow.steps as step (step.id)}
		{@const state = workflow.stepStates[step.id]}
		{@const isActive = state === 'active'}
		<div class={cn(tabVariants({ viewing: viewId === step.id, state }), 'hover:text-fg justify-between')}>
			<button
				disabled={!workflow.canGoBack}
				onclick={handleBack}
				class={cn(
					'grid h-full cursor-pointer place-content-center overflow-hidden transition-all duration-200',
					isActive ? 'w-6' : 'w-0',
					isActive && workflow.canGoBack ? 'opacity-100' : 'pointer-events-none cursor-not-allowed opacity-40'
				)}
				title="Re-open previous step"
			>
				<ChevronLeft width="14" height="14" />
			</button>
			<button
				onclick={() => onViewChange?.(step.id)}
				class="flex w-20 cursor-pointer items-center justify-center px-1.5 uppercase"
			>
				{step.label}
			</button>
			<button
				disabled={!workflow.canAdvance}
				onclick={handleNext}
				class={cn(
					'grid h-full cursor-pointer place-content-center overflow-hidden transition-all duration-200',
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
