<script lang="ts">
	import type { Session } from '$lib/main';
	import { SpinBox } from '$lib/ui/kit';

	interface Props {
		session: Session;
	}

	let { session }: Props = $props();

	let gridLimX = $derived(session.fov.width * (1 - session.gridConfig.overlap));
	let gridLimY = $derived(session.fov.height * (1 - session.gridConfig.overlap));
</script>

<div
	class="flex items-center gap-2 text-[0.65rem]"
	class:opacity-70={session.gridLocked}
	class:pointer-events-none={session.gridLocked}
>
	<SpinBox
		value={session.gridConfig.x_offset_um / 1000}
		min={-gridLimX}
		max={gridLimX}
		step={0.1}
		snapValue={0.0}
		decimals={1}
		numCharacters={5}
		size="sm"
		prefix="Grid dX"
		suffix="mm"
		onChange={(value: number) => {
			if (session.gridLocked) return;
			session.setGridOffset(value * 1000, session.gridConfig.y_offset_um);
		}}
	/>
	<SpinBox
		value={session.gridConfig.y_offset_um / 1000}
		min={-gridLimY}
		max={gridLimY}
		snapValue={0.0}
		step={0.1}
		decimals={1}
		numCharacters={5}
		size="sm"
		prefix="Grid dY"
		suffix="mm"
		onChange={(value: number) => {
			if (session.gridLocked) return;
			session.setGridOffset(session.gridConfig.x_offset_um, value * 1000);
		}}
	/>
	<SpinBox
		value={session.gridConfig.overlap}
		min={0}
		max={0.5}
		snapValue={0.1}
		step={0.01}
		decimals={2}
		numCharacters={5}
		size="sm"
		prefix="Overlap"
		suffix="%"
		onChange={(value: number) => {
			if (session.gridLocked) return;
			session.setGridOverlap(value);
		}}
	/>
</div>
