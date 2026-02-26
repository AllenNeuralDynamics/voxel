<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const workflowTabsVariants = tv({
		base: 'flex items-center  border border-border rounded-3xl'
	});

	export type WorkflowTabsVariants = VariantProps<typeof workflowTabsVariants>;

	const tabVariants = tv({
		base: 'flex flex-1 items-center gap-2 px-3 py-1.5 text-[0.65rem] uppercase tracking-wide transition-colors text-muted-foreground rounded-xl transition-colors',
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
	import Icon from '@iconify/svelte';
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
	<button
		disabled={!workflow.canGoBack}
		onclick={handleBack}
		class={cn(
			'flex items-center justify-center border-r border-transparent px-2 py-1.5 text-muted-foreground transition-colors',
			!workflow.canGoBack ? 'cursor-not-allowed opacity-40' : 'hover:bg-muted hover:text-foreground'
		)}
		title="Re-open previous step"
	>
		<Icon icon="mdi:chevron-left" width="14" height="14" />
	</button>
	{#each workflow.steps as step (step.id)}
		{@const state = workflow.stepStates[step.id]}
		<button
			onclick={() => (viewId = step.id)}
			class={cn(tabVariants({ viewing: viewId === step.id, state }), 'cursor-pointer hover:text-foreground')}
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
					<Icon icon="mdi:check" width="8" height="8" class="pointer-events-none" />
				{/if}
			</span>
			{step.label}
		</button>
	{/each}
	<button
		disabled={!workflow.canAdvance}
		onclick={handleNext}
		class={cn(
			'flex items-center justify-center border-l border-transparent px-2 py-1.5 text-muted-foreground transition-colors',
			!workflow.canAdvance ? 'cursor-not-allowed opacity-40' : 'hover:bg-muted hover:text-foreground'
		)}
		title="Commit step and advance"
	>
		<Icon icon="mdi:chevron-right" width="14" height="14" />
	</button>
</div>
