import type { StepState, WorkflowStepConfig, AppStatus } from './types';
import type { Client } from './client.svelte';

export class Workflow {
	#unsubscribe: () => void;

	steps = $state<WorkflowStepConfig[]>([]);
	committed = $state<string | null>(null);

	committedIndex: number = $derived.by(() => {
		if (this.committed === null) return -1;
		for (let i = 0; i < this.steps.length; i++) {
			if (this.steps[i].id === this.committed) return i;
		}
		return -1;
	});

	activeIndex: number = $derived(Math.min(this.committedIndex + 1, this.steps.length - 1));
	activeStep: WorkflowStepConfig = $derived(this.steps[this.activeIndex]);
	allCommitted: boolean = $derived(this.committedIndex === this.steps.length - 1);

	stepStates: Record<string, StepState> = $derived.by(() => {
		const ci = this.committedIndex;
		const result: Record<string, StepState> = {};
		for (let i = 0; i < this.steps.length; i++) {
			if (i <= ci) result[this.steps[i].id] = 'committed';
			else if (i === ci + 1) result[this.steps[i].id] = 'active';
			else result[this.steps[i].id] = 'pending';
		}
		return result;
	});

	canGoBack: boolean = $derived(this.committedIndex >= 0);
	canAdvance: boolean = $derived(!this.allCommitted);

	constructor(client: Client) {
		this.#unsubscribe = client.on('status', (status) => this.#handleStatus(status));
	}

	destroy(): void {
		this.#unsubscribe();
	}

	#handleStatus = (status: AppStatus): void => {
		this.committed = status.session?.workflow_committed ?? null;
	};
}
