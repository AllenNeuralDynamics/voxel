import type { Component } from 'svelte';
import type { Session } from '$lib/main';
import type { LayerVisibility } from '$lib/main/types';
import { GridLines, StackLight, ImageLight } from '$lib/icons';
import { compositeFullFrames } from '$lib/main/preview.svelte';
import { watch } from 'runed';

// ── Layer visibility (module-level singleton) ────────────────────

let _layerVisibility = $state<LayerVisibility>({ grid: true, stacks: true, path: true, fov: true, thumbnail: true });

export const layerVisibility = {
	get value() {
		return _layerVisibility;
	},
	toggle(key: keyof LayerVisibility) {
		_layerVisibility = { ..._layerVisibility, [key]: !_layerVisibility[key] };
	}
};

export const layerItems: { key: keyof LayerVisibility; color: string; Icon: Component; title: string }[] = [
	{ key: 'grid', color: 'text-fg-muted', Icon: GridLines, title: 'Toggle grid' },
	{ key: 'stacks', color: 'text-info', Icon: StackLight, title: 'Toggle stacks' },
	{ key: 'thumbnail', color: 'text-success', Icon: ImageLight, title: 'Toggle thumbnail' }
];

// ── Grid lock (per-instance composable) ──────────────────────────

export interface GridLock {
	readonly forceUnlocked: boolean;
	readonly editable: boolean;
	unlock(): void;
	relock(): void;
}

export function createGridLock(getSession: () => Session): GridLock {
	let forceUnlocked = $state(false);

	watch(
		() => getSession().activeProfileId,
		() => {
			forceUnlocked = false;
		}
	);

	return {
		get forceUnlocked() {
			return forceUnlocked;
		},
		get editable() {
			return getSession().activeStacks.length === 0 || forceUnlocked;
		},
		unlock() {
			forceUnlocked = true;
		},
		relock() {
			forceUnlocked = false;
		}
	};
}

// ── FOV thumbnail (per-instance composable) ──────────────────────

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
