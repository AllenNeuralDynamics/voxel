import type { Session } from '$lib/main';
import type { WorkflowStepConfig } from '$lib/main/types';

export class Workflow {
	#session: Session = null!;

	viewIndex = $state(0);

	steps: WorkflowStepConfig[] = $derived(this.#session.workflowSteps);

	currentIndex: number = $derived.by(() => {
		const steps = this.#session.workflowSteps;
		for (let i = 0; i < steps.length; i++) {
			if (steps[i].state !== 'completed') return i;
		}
		return steps.length - 1;
	});

	currentStep: WorkflowStepConfig = $derived(this.steps[this.currentIndex]);
	viewStep: WorkflowStepConfig = $derived(this.steps[this.viewIndex]);
	isPeeking: boolean = $derived(this.viewIndex !== this.currentIndex);
	allComplete: boolean = $derived(this.steps.every((s) => s.state === 'completed'));
	canAdvance: boolean = $derived(
		!this.isPeeking && !this.allComplete && this.currentStep?.state === 'active'
	);
	visibleSteps: WorkflowStepConfig[] = $derived(this.steps.slice(0, this.currentIndex + 1));

	constructor(session: Session) {
		this.#session = session;
	}

	view(stepId: string): void {
		const index = this.steps.findIndex((s) => s.id === stepId);
		if (index === -1) return;
		if (this.steps[index].state === 'completed' || index === this.currentIndex) {
			this.viewIndex = index;
		}
	}

	next(): void {
		if (this.isPeeking || this.allComplete) return;
		this.#session.workflowNext();
		// Optimistic: advance viewIndex to next step
		if (this.currentIndex + 1 < this.steps.length) {
			this.viewIndex = this.currentIndex + 1;
		}
	}

	reopen(stepId: string): void {
		const index = this.steps.findIndex((s) => s.id === stepId);
		if (index === -1) return;
		this.#session.workflowReopen(stepId);
		// Optimistic: move view to reopened step
		this.viewIndex = index;
	}

	isViewing(stepId: string): boolean {
		return this.viewStep?.id === stepId;
	}

	isCurrent(stepId: string): boolean {
		return this.currentStep?.id === stepId;
	}
}
