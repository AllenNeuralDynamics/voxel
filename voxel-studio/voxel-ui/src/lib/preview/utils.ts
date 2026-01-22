/**
 * Computes the min and max levels for "auto levels" based on the 1st and 99th percentiles.
 * @param histogram The histogram data.
 * @returns An object with the new min and max levels (normalized 0-1), or null if input is invalid.
 */
export function computeAutoLevels(histogram: number[]): { min: number; max: number } | null {
	if (!histogram || histogram.length === 0) {
		return null;
	}

	const numBins = histogram.length;
	const totalPixels = histogram.reduce((sum, count) => sum + count, 0);

	if (totalPixels === 0) {
		return { min: 0, max: 1 };
	}

	const p1Threshold = totalPixels * 0.01;
	const p99Threshold = totalPixels * 0.99;

	let cumulative = 0;
	let minBin = 0;
	let maxBin = numBins - 1;

	// Find min (1st percentile)
	for (let i = 0; i < numBins; i++) {
		cumulative += histogram[i];
		if (cumulative >= p1Threshold) {
			minBin = i;
			break;
		}
	}

	// Find max (99th percentile)
	cumulative = 0;
	for (let i = 0; i < numBins; i++) {
		cumulative += histogram[i];
		if (cumulative >= p99Threshold) {
			maxBin = i;
			break;
		}
	}

	// Ensure min is not greater than max
	if (minBin >= maxBin) {
		if (minBin > 0) {
			minBin = maxBin - 1;
		} else {
			maxBin = minBin + 1;
		}
	}

	return {
		min: minBin / (numBins - 1),
		max: maxBin / (numBins - 1)
	};
}
