export function clampTopLeft(value: number, viewSize: number): number {
	return Math.max(0, Math.min(value, 1 - viewSize));
}

export async function getWebGPUDevice(lossHandler?: (info: GPUDeviceLostInfo) => void): Promise<GPUDevice> {
	if (!navigator.gpu) {
		throw new Error('WebGPU is not supported in this browser.');
	}

	const adapter = await navigator.gpu.requestAdapter();
	if (!adapter) {
		throw new Error('Failed to get GPU adapter.');
	}
	const device = await adapter?.requestDevice();

	device?.lost.then((info) => {
		if (info.reason !== 'destroyed') {
			console.warn('WebGPU device lost reason:', info.reason);
			lossHandler?.(info);
		}
	});

	return device;
}
