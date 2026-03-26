<script lang="ts">
	import type { Session } from '$lib/main';
	import { onMount } from 'svelte';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	const PANEL_WIDTH = 64;

	let profileStacks = $derived(session.activeStacks);

	let containerRef = $state<HTMLDivElement | null>(null);
	let panelHeight = $state(250);

	let target = $state<number | null>(null);

	let fovZ = $derived(session.stage.z ? session.stage.z.position - session.stage.z.lowerLimit : 0);
	let zLineY = $derived((1 - fovZ / session.stage.depth) * panelHeight - 1);

	let displayValue = $derived(session.stage.z?.isMoving && target !== null ? target : (session.stage.z?.position ?? 0));

	function oninput(e: Event) {
		const v = parseFloat((e.target as HTMLInputElement).value);
		target = v;
		session.stage.z?.move(v);
	}

	onMount(() => {
		if (!containerRef) return;
		const observer = new ResizeObserver(([entry]) => {
			const h = entry.contentRect.height;
			if (h > 0) panelHeight = h;
		});
		observer.observe(containerRef);
		return () => observer.disconnect();
	});
</script>

<div
	bind:this={containerRef}
	class="relative h-full flex-none border border-fg-faint/70 transition-colors duration-300 ease-in-out hover:bg-elevated/75"
	style="width: {PANEL_WIDTH}px"
>
	<p class="absolute top-1 right-1 z-10 text-xs text-fg-muted">Z</p>

	{#if session.stage.z}
		<input
			type="range"
			class="stage-slider absolute inset-0 z-10 h-full w-full"
			style:--thumb-length="{PANEL_WIDTH}px"
			min={session.stage.z.lowerLimit}
			max={session.stage.z.upperLimit}
			step={0.1}
			value={displayValue}
			disabled={session.stage.z.isMoving}
			{oninput}
		/>
	{/if}

	<svg
		viewBox="0 0 {PANEL_WIDTH} {panelHeight}"
		class="pointer-none absolute inset-0 z-0"
		preserveAspectRatio="none"
		width="100%"
		height="100%"
	>
		{#each profileStacks as stack (`z_${stack.row}_${stack.col}`)}
			{@const selected = session.isTileSelected(stack.row, stack.col)}
			{@const z0Y =
				(1 - (stack.z_start_um / 1000 - session.stage.z.lowerLimit) / session.stage.depth) * panelHeight - 1}
			{@const z1Y = (1 - (stack.z_end_um / 1000 - session.stage.z.lowerLimit) / session.stage.depth) * panelHeight - 1}
			<g
				data-stack-status={stack.status}
				class="text-(--stack-status)"
				stroke-width={selected ? '1.5' : '0.5'}
				stroke="currentColor"
				opacity={selected ? 1 : 0.3}
			>
				<line class="nss" x1="0" y1={z0Y} x2={PANEL_WIDTH} y2={z0Y} />
				<line class="nss" x1="0" y1={z1Y} x2={PANEL_WIDTH} y2={z1Y} />
			</g>
		{/each}
		<line
			x1="0"
			y1={zLineY}
			x2={PANEL_WIDTH}
			y2={zLineY}
			class="nss"
			stroke-width="1"
			stroke={session.stage.z?.isMoving ? 'var(--color-danger)' : 'var(--color-success)'}
		>
			<title>Z: {session.stage.z?.position.toFixed(1)} mm</title>
		</line>
	</svg>
</div>

<style>
	.stage-slider {
		-webkit-appearance: none;
		appearance: none;
		writing-mode: vertical-rl;
		direction: rtl;
		cursor: pointer;
		margin: 0;
		padding: 0;
		border: none;
		background-color: transparent;
		--_track-color: var(--color-border);
		--_track-width: 1px;

		&::-webkit-slider-runnable-track {
			background: transparent;
			border-radius: 0;
		}
		&::-moz-range-track {
			background: transparent;
			border-radius: 0;
		}
		&::-webkit-slider-thumb {
			-webkit-appearance: none;
			appearance: none;
			inline-size: 1px;
			block-size: var(--thumb-length);
			border-radius: 1px;
			cursor: pointer;
			background: transparent;
		}
		&::-moz-range-thumb {
			appearance: none;
			inline-size: 1px;
			block-size: var(--thumb-length);
			border: none;
			border-radius: 1px;
			cursor: pointer;
			background: transparent;
		}
		&:disabled {
			cursor: not-allowed;
			&::-webkit-slider-thumb {
				background: var(--color-danger);
			}
			&::-moz-range-thumb {
				background: var(--color-danger);
			}
		}
	}
</style>
