<script lang="ts">
	import { Sheet } from '$lib/ui/kit';
	import ThemePicker from './ThemePicker.svelte';

	let { open = $bindable(false) }: { open?: boolean } = $props();
</script>

<Sheet.Root bind:open>
	<Sheet.Content side="right" overlay={false} class="w-80 sm:max-w-80">
		<Sheet.Header>
			<Sheet.Title>Appearance</Sheet.Title>
			<Sheet.Description class="text-sm">Choose a color theme for the interface.</Sheet.Description>
		</Sheet.Header>
		<div class="px-4">
			<ThemePicker />
		</div>
	</Sheet.Content>
</Sheet.Root>
