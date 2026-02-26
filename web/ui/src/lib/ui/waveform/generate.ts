import type { Waveform } from '$lib/main';

export interface WaveformTraces {
	/** Time values in seconds. */
	time: number[];
	/** Device ID → voltage values (same length as time). */
	traces: Record<string, number[]>;
}

/**
 * Generate voltage traces for all waveforms over a single frame.
 *
 * @param waveforms - Device ID → waveform definition.
 * @param duration - Frame active duration in seconds.
 * @param restTime - Rest period after the active duration in seconds.
 * @param numPoints - Number of sample points to generate (default 500).
 */
export function generateTraces(
	waveforms: Record<string, Waveform>,
	duration: number,
	restTime: number,
	numPoints = 500
): WaveformTraces {
	const totalTime = duration + restTime;
	const dt = totalTime / (numPoints - 1);
	const time = Array.from({ length: numPoints }, (_, i) => i * dt);
	const traces: Record<string, number[]> = {};

	for (const [deviceId, waveform] of Object.entries(waveforms)) {
		traces[deviceId] = time.map((t) => sampleWaveform(waveform, t, duration));
	}

	return { time, traces };
}

/**
 * Compute voltage for a single waveform at a given time.
 *
 * @param waveform - Waveform definition.
 * @param t - Time in seconds (0 to duration + restTime).
 * @param duration - Active frame duration in seconds.
 */
export function sampleWaveform(waveform: Waveform, t: number, duration: number): number {
	const { min: vMin, max: vMax } = waveform.voltage;
	const restV = waveform.rest_voltage ?? vMin;

	// Outside active duration → rest voltage
	if (t > duration) return restV;

	const norm = t / duration; // 0..1 within the active period
	const { min: wMin, max: wMax } = waveform.window;

	// Outside window → rest voltage
	if (norm < wMin || norm > wMax) return restV;

	const windowDur = (wMax - wMin) * duration;
	const tWindow = (norm - wMin) * duration; // seconds since window start

	switch (waveform.type) {
		case 'pulse':
			return vMax;

		case 'square': {
			const freq = Number(waveform.frequency || 0);
			const dc = waveform.duty_cycle;
			if (freq > 0) {
				const phase = (tWindow * freq) % 1;
				return phase < dc ? vMax : vMin;
			}
			// No frequency — single pulse with duty_cycle ratio
			return tWindow / windowDur < dc ? vMax : vMin;
		}

		case 'sawtooth': {
			const freq = Number(waveform.frequency);
			const phase = (tWindow * freq) % 1;
			return vMin + (vMax - vMin) * phase;
		}

		case 'sine': {
			const freq = Number(waveform.frequency);
			const phase = waveform.phase ?? 0;
			const val = Math.sin(2 * Math.PI * freq * tWindow + phase);
			// Map [-1, 1] → [vMin, vMax]
			return vMin + (vMax - vMin) * (val + 1) / 2;
		}

		case 'triangle': {
			const freq = Number(waveform.frequency);
			const sym = waveform.symmetry ?? 0.5;
			const phase = (tWindow * freq) % 1;
			const val = phase < sym ? phase / sym : 1 - (phase - sym) / (1 - sym);
			return vMin + (vMax - vMin) * val;
		}

		case 'multi_point': {
			const pts = waveform.points;
			if (!pts.length) return restV;
			const normWindow = tWindow / windowDur; // 0..1 within window
			// Clamp to first/last point
			if (normWindow <= pts[0][0]) return vMin + (vMax - vMin) * pts[0][1];
			if (normWindow >= pts[pts.length - 1][0]) return vMin + (vMax - vMin) * pts[pts.length - 1][1];
			// Linear interpolation between surrounding points
			for (let i = 0; i < pts.length - 1; i++) {
				if (normWindow >= pts[i][0] && normWindow <= pts[i + 1][0]) {
					const frac = (normWindow - pts[i][0]) / (pts[i + 1][0] - pts[i][0]);
					const normV = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * frac;
					return vMin + (vMax - vMin) * normV;
				}
			}
			return restV;
		}

		case 'csv':
			// Cannot compute client-side — show rest voltage
			return restV;
	}
}

/**
 * Compute the global voltage range across all waveforms.
 */
export function voltageRange(waveforms: Record<string, Waveform>): { min: number; max: number } {
	let min = Infinity;
	let max = -Infinity;
	for (const wf of Object.values(waveforms)) {
		if (wf.voltage.min < min) min = wf.voltage.min;
		if (wf.voltage.max > max) max = wf.voltage.max;
		const rest = wf.rest_voltage ?? wf.voltage.min;
		if (rest < min) min = rest;
		if (rest > max) max = rest;
	}
	// Add a small margin
	const margin = (max - min) * 0.05 || 0.1;
	return { min: min - margin, max: max + margin };
}
