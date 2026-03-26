<script lang="ts">
	import type { Session } from '$lib/main';
	import { buttonVariants } from '$lib/ui/kit/Button.svelte';
	import { DropdownMenu } from '$lib/ui/kit';
	import { ChevronDown } from '$lib/icons';
	import { cn } from '$lib/utils';

	interface Props {
		session: Session;
		class?: string;
	}

	let { session, class: className }: Props = $props();

	const isPreviewing = $derived(session.preview.isPreviewing);
	// TODO: replace with real session.mode === 'acquiring' once wired to WS
	let fakeAcquiring = $state(false);
	const isAcquiring = $derived(fakeAcquiring);
	const canAcquire = $derived(session.plan.stacks.some((s) => s.status === 'planned'));
	const isRunning = $derived(isPreviewing || isAcquiring);

	function handleStartPreview() {
		session.preview.startPreview();
	}

	function handleStopPreview() {
		session.preview.stopPreview();
	}

	function handleStartAcquisition() {
		// TODO: wire to acq/start WS topic
		fakeAcquiring = true;
	}

	function handleStopAcquisition() {
		// TODO: wire to acq/stop WS topic
		fakeAcquiring = false;
	}

	function handleStop() {
		if (isAcquiring) handleStopAcquisition();
		else if (isPreviewing) handleStopPreview();
	}

	const base = buttonVariants({ variant: 'success', size: 'lg' });
</script>

{#if isRunning}
	<button
		class={buttonVariants({ variant: 'danger', size: 'lg', class: cn('w-40 rounded-md', className) })}
		onclick={handleStop}
	>
		{isAcquiring ? 'Stop Acquisition' : 'Stop Preview'}
	</button>
{:else}
	<DropdownMenu.Root>
		<DropdownMenu.Trigger class={cn(base, 'w-40 justify-between rounded-md', className)}>
			Start Imaging
			<ChevronDown width="14" height="14" />
		</DropdownMenu.Trigger>
		<DropdownMenu.Content align="end" class="w-40">
			<DropdownMenu.Item onclick={handleStartPreview}>Preview</DropdownMenu.Item>
			<DropdownMenu.Item onclick={handleStartAcquisition} disabled={!canAcquire}>Acquisition</DropdownMenu.Item>
		</DropdownMenu.Content>
	</DropdownMenu.Root>
{/if}
