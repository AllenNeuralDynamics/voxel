export class WorkflowStep {
	readonly id: string;
	readonly label: string;
	readonly #canComplete: () => boolean;

	completed = $state(false);
	readonly = $derived(this.completed);

	constructor(id: string, label: string, canComplete: () => boolean = () => true) {
		this.id = id;
		this.label = label;
		this.#canComplete = canComplete;
	}

	canComplete(): boolean {
		return this.#canComplete();
	}

	complete(): boolean {
		if (!this.canComplete()) return false;
		this.completed = true;
		return true;
	}

	reopen(): void {
		this.completed = false;
	}
}

export class Workflow {
	readonly steps: WorkflowStep[];
	currentIndex = $state(0);
	viewIndex = $state(0);

	currentStep = $derived.by(() => this.steps[this.currentIndex]);
	viewStep = $derived.by(() => this.steps[this.viewIndex]);
	isFirst = $derived.by(() => this.currentIndex === 0);
	isLast = $derived.by(() => this.currentIndex === this.steps.length - 1);
	isPeeking = $derived.by(() => this.viewIndex !== this.currentIndex);
	allComplete = $derived.by(() => this.steps.every((s) => s.completed));
	canAdvance = $derived.by(() => !this.isPeeking && !this.allComplete && this.currentStep.canComplete());
	visibleSteps = $derived.by(() => this.steps.slice(0, this.currentIndex + 1));

	constructor(steps: WorkflowStep[]) {
		this.steps = steps;
	}

	/** Navigate to a completed step to peek, or snap back to current. */
	view(stepId: string): void {
		const index = this.steps.findIndex((s) => s.id === stepId);
		if (index === -1) return;
		if (this.steps[index].completed || index === this.currentIndex) {
			this.viewIndex = index;
		}
	}

	next(): void {
		if (this.isPeeking || this.allComplete) return;
		if (!this.currentStep.complete()) return;
		if (!this.isLast) {
			this.currentIndex++;
			this.viewIndex = this.currentIndex;
		}
	}

	reopen(stepId: string): void {
		const index = this.steps.findIndex((s) => s.id === stepId);
		if (index === -1) return;

		// Invalidate this step and all downstream
		for (let i = index; i < this.steps.length; i++) {
			this.steps[i].reopen();
		}

		this.currentIndex = index;
		this.viewIndex = index;
	}

	isViewing(stepId: string): boolean {
		return this.viewStep.id === stepId;
	}

	isCurrent(stepId: string): boolean {
		return this.currentStep.id === stepId;
	}
}
