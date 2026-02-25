import type { StepState, WorkflowStepConfig, AppStatus } from './types';
import type { Client } from './client.svelte';

export class Workflow {
	#client: Client;
	#unsubscribe: () => void;

	steps = $state<WorkflowStepConfig[]>([]);
	committed = $state<string | null>(null);

	#committedIndex: number = $derived.by(() => {
		if (this.committed === null) return -1;
		for (let i = 0; i < this.steps.length; i++) {
			if (this.steps[i].id === this.committed) return i;
		}
		return -1;
	});

	activeIndex: number = $derived(Math.min(this.#committedIndex + 1, this.steps.length - 1));
	activeStep: WorkflowStepConfig = $derived(this.steps[this.activeIndex]);
	allCommitted: boolean = $derived(this.#committedIndex === this.steps.length - 1);

	stepStates: Record<string, StepState> = $derived.by(() => {
		const ci = this.#committedIndex;
		const result: Record<string, StepState> = {};
		for (let i = 0; i < this.steps.length; i++) {
			if (i <= ci) result[this.steps[i].id] = 'committed';
			else if (i === ci + 1) result[this.steps[i].id] = 'active';
			else result[this.steps[i].id] = 'pending';
		}
		return result;
	});

	canGoBack: boolean = $derived(this.#committedIndex >= 0);
	canAdvance: boolean = $derived(!this.allCommitted);

	constructor(client: Client) {
		this.#client = client;
		this.#unsubscribe = client.on('status', (status) => this.#handleStatus(status));
	}

	destroy(): void {
		this.#unsubscribe();
	}

	#handleStatus = (status: AppStatus): void => {
		this.steps = status.session?.workflow_steps ?? [];
		this.committed = status.session?.workflow_committed ?? null;
	};

	back(): string | null {
		if (!this.canGoBack) return null;
		const stepId = this.steps[this.#committedIndex].id;
		this.#client.send({ topic: 'workflow/reopen', payload: { step_id: stepId } });
		return stepId;
	}

	next(): string | null {
		if (!this.canAdvance) return null;
		this.#client.send({ topic: 'workflow/next' });
		const nextIdx = this.activeIndex + 1;
		if (nextIdx < this.steps.length) {
			return this.steps[nextIdx].id;
		}
		return null;
	}
}
