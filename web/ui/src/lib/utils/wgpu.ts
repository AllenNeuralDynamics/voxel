export async function getWebGPUDevice(lossHandler?: (info: GPUDeviceLostInfo) => void): Promise<GPUDevice> {
	if (!navigator.gpu) {
		throw new Error('WebGPU is not supported in this browser.');
	}

	// Retry with backoff - GPU adapter may need time to become available after page load
	const maxRetries = 3;
	const baseDelayMs = 150;

	for (let attempt = 0; attempt < maxRetries; attempt++) {
		if (attempt > 0) {
			const delay = baseDelayMs * Math.pow(2, attempt - 1);
			await new Promise((resolve) => setTimeout(resolve, delay));
		}

		const adapter = await navigator.gpu.requestAdapter();
		if (adapter) {
			const device = await adapter.requestDevice();

			device.lost.then((info) => {
				if (info.reason !== 'destroyed') {
					console.warn('[WebGPU] Device lost:', info.reason);
					lossHandler?.(info);
				}
			});

			return device;
		}
	}

	throw new Error('Failed to get GPU adapter after retries.');
}
