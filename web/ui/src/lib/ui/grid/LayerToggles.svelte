<script lang="ts">
	import Icon from '@iconify/svelte';
	import type { App } from '$lib/app';

	interface Props {
		app: App;
		showThumbnail?: boolean;
	}

	let { app, showThumbnail = $bindable(true) }: Props = $props();

	function toggleLayer(key: keyof typeof app.layerVisibility) {
		app.layerVisibility = { ...app.layerVisibility, [key]: !app.layerVisibility[key] };
	}
</script>

{#snippet toggle(
	active: boolean,
	activeColor: string,
	icon: string,
	title: string,
	onclick: () => void,
	disabled?: boolean
)}
	<button
		{onclick}
		{disabled}
		class="rounded p-1 transition-colors {active
			? `${activeColor} hover:bg-zinc-700`
			: 'text-zinc-500 hover:bg-zinc-700 hover:text-zinc-300'} disabled:cursor-not-allowed disabled:opacity-50"
		{title}
	>
		<Icon {icon} width="14" height="14" />
	</button>
{/snippet}

<div class="flex gap-0.5 rounded p-1">
	{@render toggle(app.layerVisibility.grid, 'text-blue-400', 'mdi:grid', 'Toggle grid', () => toggleLayer('grid'))}
	{@render toggle(app.layerVisibility.stacks, 'text-purple-400', 'mdi:layers', 'Toggle stacks', () =>
		toggleLayer('stacks')
	)}
	{@render toggle(app.layerVisibility.path, 'text-fuchsia-400', 'mdi:vector-polyline', 'Toggle acquisition path', () =>
		toggleLayer('path')
	)}
	{@render toggle(app.layerVisibility.fov, 'text-emerald-400', 'mdi:crosshairs', 'Toggle FOV', () =>
		toggleLayer('fov')
	)}
	{@render toggle(
		showThumbnail && app.layerVisibility.fov,
		'text-cyan-400',
		'mdi:image',
		'Toggle thumbnail',
		() => (showThumbnail = !showThumbnail),
		!app.layerVisibility.fov
	)}
</div>
