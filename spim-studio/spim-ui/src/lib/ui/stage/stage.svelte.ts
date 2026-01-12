/**
import type { StageConfig } from '$lib/core';
import type { App } from '$lib/app';
import type { Previewer } from '$lib/preview';

// Inline types
interface GridConfig {
	originX: number;
	originY: number;
	numCellsX: number;
	numCellsY: number;
	overlap: number;
}

interface FOVConfig {
	x: number;
	y: number;
	w: number;
	h: number;
}

interface ZRange {
	min: number;
	max: number;
}


export class Axis {
	readonly #app: App;
	readonly #deviceId: string;

	constructor(app: App, deviceId: string) {
		this.#app = app;
		this.#deviceId = deviceId;
	}

	// Check if device is connected
	isConnected = $derived.by(() => {
		return this.#app.devices.getDevice(this.#deviceId)?.connected ?? false;
	});

	// Derived state properties
	position = $derived.by(() => {
		const val = this.#app.devices.getPropertyValue(this.#deviceId, 'position_mm');
		return typeof val === 'number' ? val : 0;
	});

	lowerLimit = $derived.by(() => {
		const val = this.#app.devices.getPropertyValue(this.#deviceId, 'lower_limit_mm');
		return typeof val === 'number' ? val : 0;
	});

	upperLimit = $derived.by(() => {
		const val = this.#app.devices.getPropertyValue(this.#deviceId, 'upper_limit_mm');
		return typeof val === 'number' ? val : 100;
	});

	isMoving = $derived.by(() => {
		const val = this.#app.devices.getPropertyValue(this.#deviceId, 'is_moving');
		return typeof val === 'boolean' ? val : false;
	});

	// Movement methods
	move(position: number): void {
		this.#app.devices.executeCommand(this.#deviceId, 'move_abs', [position], { wait: false });
	}

	async halt(): Promise<void> {
		await this.#app.devices.executeCommand(this.#deviceId, 'halt');
	}
}

export class Stage {
	readonly #app: App;
	readonly #previewer!: Previewer;
	readonly config: StageConfig | null | undefined;

	// Stable axis instances
	readonly xAxis!: Axis | null;
	readonly yAxis!: Axis | null;
	readonly zAxis!: Axis | null;

	thumbnail = $derived(this.#previewer.thumbnailSnapshot);
	fov: FOVConfig = $derived(this.#getFOVConfig());
	zRange: ZRange = $state({ min: 0, max: 0 });
	gridConfig = $state<GridConfig>({
		originX: 0,
		originY: 0,
		numCellsX: 5,
		numCellsY: 5,
		overlap: 0.1
	});
	gridSpacingX = $derived(this.fov.w * (1 - this.gridConfig.overlap));
	gridSpacingY = $derived(this.fov.h * (1 - this.gridConfig.overlap));
	maxGridCellsX = $derived.by(() => {
		const stageWidth = this.stageWidth;
		if (!isFinite(this.fov.w) || !isFinite(stageWidth) || this.fov.w <= 0 || stageWidth <= 0) return 1;
		return Math.max(1, Math.floor(stageWidth / (this.fov.w * (1 - this.gridConfig.overlap))) + 1);
	});

	maxGridCellsY = $derived.by(() => {
		const stageHeight = this.stageHeight;
		if (!isFinite(this.fov.h) || !isFinite(stageHeight) || this.fov.h <= 0 || stageHeight <= 0) return 1;
		return Math.max(1, Math.floor(stageHeight / (this.fov.h * (1 - this.gridConfig.overlap))) + 1);
	});
	stageWidth = $derived(this.xAxis ? this.xAxis.upperLimit - this.xAxis.lowerLimit : 100);
	stageHeight = $derived(this.yAxis ? this.yAxis.upperLimit - this.yAxis.lowerLimit : 100);
	stageDepth = $derived(this.zAxis ? this.zAxis.upperLimit - this.zAxis.lowerLimit : 100);

	constructor(app: App, previewer: Previewer) {
		this.#app = app;
		this.#previewer = previewer;

		// Get stage configuration
		this.config = app.config?.stage;

		// Create axis instances if configured
		this.xAxis = this.config?.x ? new Axis(app, this.config.x) : null;
		this.yAxis = this.config?.y ? new Axis(app, this.config.y) : null;
		this.zAxis = this.config?.z ? new Axis(app, this.config.z) : null;

		// Initialize zRange to the full z-axis range
		if (this.zAxis) {
			this.zRange.min = this.zAxis.lowerLimit;
			this.zRange.max = this.zAxis.upperLimit;
		}

		// Enable thumbnails when Stage is created
		this.#previewer.enableThumbnails = true;
	}

	#getFOVConfig() {
		return {
			x: this.xAxis ? this.xAxis.position - this.xAxis.lowerLimit : 0,
			y: this.yAxis ? this.yAxis.position - this.yAxis.lowerLimit : 0,
			w: this.#app.activeProfile?.fovDimensions?.width ?? 5,
			h: this.#app.activeProfile?.fovDimensions?.height ?? 5
		};
	}

	// Handle grid cell click to move stage
	async moveToGridCell(gridX: number, gridY: number): Promise<void> {
		const xAxis = this.xAxis;
		const yAxis = this.yAxis;

		if (!xAxis || !yAxis) return;
		if (xAxis.isMoving || yAxis.isMoving) return;

		// Calculate absolute position from grid coordinates with origin offset
		const targetX = xAxis.lowerLimit + this.gridConfig.originX + gridX * this.gridSpacingX;
		const targetY = yAxis.lowerLimit + this.gridConfig.originY + gridY * this.gridSpacingY;

		// Move both axes simultaneously
		xAxis.move(targetX);
		yAxis.move(targetY);
	}

	// Halt all stage axes
	async halt(): Promise<void> {
		const haltPromises = [];

		if (this.xAxis) {
			haltPromises.push(this.xAxis.halt());
		}
		if (this.yAxis) {
			haltPromises.push(this.yAxis.halt());
		}
		if (this.zAxis) {
			haltPromises.push(this.zAxis.halt());
		}

		await Promise.all(haltPromises);
	}

	// Clamp grid cells when max changes
	clampGridCells(): void {
		this.gridConfig.numCellsX = Math.min(this.gridConfig.numCellsX, this.maxGridCellsX);
		this.gridConfig.numCellsY = Math.min(this.gridConfig.numCellsY, this.maxGridCellsY);
	}

	// Cleanup method to disable thumbnails
	destroy(): void {
		this.#previewer.enableThumbnails = false;
	}
}
*/
