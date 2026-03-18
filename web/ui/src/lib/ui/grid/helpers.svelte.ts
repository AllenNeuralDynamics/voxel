import type { Session } from '$lib/main';
import { compositeFullFrames } from '$lib/main/preview.svelte';
import { watch } from 'runed';

const FOV_RESOLUTION = 256;

export function createFovThumbnail(getSession: () => Session) {
	let thumbnail = $state('');
	let needsRedraw = false;
	let animFrameId: number | null = null;

	const offscreen = document.createElement('canvas');
	offscreen.width = FOV_RESOLUTION;
	const ctx = offscreen.getContext('2d')!;

	$effect(() => {
		const session = getSession();
		const aspect = session.fov.width / session.fov.height;
		if (aspect > 0 && Number.isFinite(aspect)) {
			offscreen.height = Math.round(FOV_RESOLUTION / aspect);
		}
	});

	watch(
		() => getSession().preview?.redrawGeneration,
		() => {
			needsRedraw = true;
		}
	);

	function frameLoop() {
		const session = getSession();
		if (needsRedraw && session.preview) {
			needsRedraw = false;
			const hasFrames = session.preview.channels.some((ch) => ch.visible && ch.frame);
			if (hasFrames) {
				compositeFullFrames(ctx, offscreen, session.preview.channels);
				thumbnail = offscreen.toDataURL('image/jpeg', 0.6);
			} else {
				thumbnail = '';
			}
		}
		animFrameId = requestAnimationFrame(frameLoop);
	}

	$effect(() => {
		frameLoop();
		return () => {
			if (animFrameId !== null) cancelAnimationFrame(animFrameId);
		};
	});

	return {
		get thumbnail() {
			return thumbnail;
		}
	};
}
