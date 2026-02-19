<script lang="ts">
    import { Tooltip } from "bits-ui";
    import Icon from "@iconify/svelte";
    import type { PreviewFrameInfo } from "$lib/main";

    interface ChannelFrameInfo {
        name: string;
        label: string | null;
        frameInfo: PreviewFrameInfo;
    }

    interface Props {
        frameInfo: PreviewFrameInfo | null;
        visibleChannels: ChannelFrameInfo[];
    }

    let { frameInfo, visibleChannels }: Props = $props();

    // Check if all channels have matching frame info
    let hasMismatch = $derived.by(() => {
        if (visibleChannels.length <= 1) return false;
        const first = visibleChannels[0].frameInfo;
        if (!first) return false;
        return visibleChannels.some((c) => {
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
            class="flex items-center rounded p-1 transition-colors {hasMismatch
                ? 'text-amber-400 hover:bg-amber-950/50'
                : 'text-zinc-300 hover:bg-zinc-800'}"
            aria-label="Preview info"
        >
            {#if hasMismatch}
                <Icon icon="mdi:alert" width="14" height="14" />
            {:else}
                <Icon icon="mdi:information-outline" width="14" height="14" />
            {/if}
        </Tooltip.Trigger>
        <Tooltip.Content
            class="z-50 w-64 rounded-md border border-zinc-700 bg-zinc-900 p-3 text-left text-xs text-zinc-200 shadow-xl outline-none"
            sideOffset={4}
            align="end"
        >
            {#if frameInfo}
                <div class="space-y-2">
                    <p class="text-sm font-semibold text-zinc-100">
                        Preview Canvas
                    </p>

                    <div
                        class="space-y-1 border-t border-zinc-800 pt-2 text-[0.7rem] text-zinc-300"
                    >
                        <div class="flex justify-between gap-2">
                            <span class="text-zinc-400">Preview Size</span>
                            <span class="text-right text-zinc-200"
                                >{frameInfo.preview_width} × {frameInfo.preview_height}</span
                            >
                        </div>
                    </div>

                    {#if visibleChannels.length > 0}
                        <div
                            class="space-y-1 border-t border-zinc-800 pt-2 text-[0.7rem] text-zinc-300"
                        >
                            {#if hasMismatch}
                                <div
                                    class="mb-1 flex items-center gap-1.5 text-amber-400"
                                >
                                    <Icon
                                        icon="mdi:alert"
                                        width="12"
                                        height="12"
                                    />
                                    <span class="font-medium"
                                        >Frame Size Mismatch</span
                                    >
                                </div>
                            {/if}
                            <div class="space-y-1">
                                {#each visibleChannels as channel (channel.name)}
                                    <div class="flex justify-between gap-2">
                                        <span class="text-zinc-400"
                                            >{channel.label ??
                                                channel.name}</span
                                        >
                                        <span class="text-right text-zinc-200"
                                            >{channel.frameInfo.full_width} × {channel
                                                .frameInfo.full_height}</span
                                        >
                                    </div>
                                {/each}
                            </div>
                        </div>
                    {/if}
                </div>
            {:else}
                <div>
                    <p class="text-sm font-semibold text-zinc-100">
                        Preview Canvas
                    </p>
                    <p class="mt-1 text-xs text-zinc-400">
                        No frames available
                    </p>
                </div>
            {/if}
        </Tooltip.Content>
    </Tooltip.Root>
</Tooltip.Provider>
