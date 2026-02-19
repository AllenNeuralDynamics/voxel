<script lang="ts">
	import { Tooltip } from 'bits-ui';
	import Icon from '@iconify/svelte';
	import type { PreviewState } from '$lib/main';

	interface Props {
		previewer: PreviewState;
	}

	let { previewer }: Props = $props();

	let visibleChannels = $derived(previewer.channels.filter((c) => c.visible && c.latestFrameInfo));
	let frameInfo = $derived(visibleChannels[0]?.latestFrameInfo ?? null);

	let channelFrameInfos = $derived(
		visibleChannels.map((c) => ({
			name: c.name ?? 'Unknown',
			label: c.label,
			frameInfo: c.latestFrameInfo!
		}))
	);

	let frameIndices = $derived(visibleChannels.map((c) => c.latestFrameInfo?.frame_idx ?? 0));
	let maxFrameIdx = $derived(Math.max(...frameIndices, 0));

	let hasMismatch = $derived.by(() => {
		if (channelFrameInfos.length <= 1) return false;
		const first = channelFrameInfos[0].frameInfo;
		if (!first) return false;
		return channelFrameInfos.some((c) => {
			const info = c.frameInfo;
			if (!info) return true;
			return (
				info.preview_width !== first.preview_width ||
				info.preview_height !== first.preview_height ||
				info.full_width !== first.full_width ||
				info.full_height !== first.full_height
			);
		});
	});
</script>

<Tooltip.Provider>
	<Tooltip.Root delayDuration={150}>
		<Tooltip.Trigger
			class="flex items-center gap-1.5 rounded p-1 font-mono text-[0.65rem] transition-colors hover:bg-accent"
			aria-label="Preview info"
		>
			{#if frameInfo}
				<span class="text-muted-foreground">Frame</span>
				<span class="text-foreground">#{maxFrameIdx}</span>
			{:else}
				<span class="text-muted-foreground">No frames</span>
			{/if}
			{#if hasMismatch}
				<Icon icon="mdi:alert" width="12" height="12" class="text-warning" />
			{/if}
		</Tooltip.Trigger>
		<Tooltip.Content
			class="z-50 w-64 rounded-md border border-border bg-popover p-3 text-left text-xs text-popover-foreground shadow-xl outline-none"
			sideOffset={4}
			align="start"
		>
			{#if frameInfo}
				<div class="space-y-2">
					<div class="space-y-1 text-[0.7rem]">
						<div class="flex justify-between gap-2">
							<span class="text-muted-foreground">Preview Size</span>
							<span class="text-right">{frameInfo.preview_width} × {frameInfo.preview_height}</span>
						</div>
					</div>
					{#if channelFrameInfos.length > 0}
						<div class="space-y-1 border-t border-border pt-2 text-[0.7rem]">
							{#if hasMismatch}
								<div class="mb-1 flex items-center gap-1.5 text-warning">
									<Icon icon="mdi:alert" width="12" height="12" />
									<span class="font-medium">Frame Size Mismatch</span>
								</div>
							{/if}
							<div class="space-y-1">
								{#each channelFrameInfos as channel (channel.name)}
									<div class="flex justify-between gap-2">
										<span class="text-muted-foreground">{channel.label ?? channel.name}</span>
										<span class="text-right"
											>{channel.frameInfo.full_width} × {channel.frameInfo.full_height}</span
										>
									</div>
								{/each}
							</div>
						</div>
					{/if}
				</div>
			{:else}
				<div>
					<p class="text-xs text-muted-foreground">No frames available</p>
				</div>
			{/if}
		</Tooltip.Content>
	</Tooltip.Root>
</Tooltip.Provider>
