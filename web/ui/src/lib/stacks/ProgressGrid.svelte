<script lang="ts">
  import type { Stack } from '$lib/config';
  import type { AcquisitionManager, StacksManager } from '$lib/stacks';

  interface Props {
    stacks: StacksManager;
    acquisition: AcquisitionManager;
    class?: string;
  }

  let { stacks, acquisition, class: className = '' }: Props = $props();

  const list = $derived(stacks.list);
  const selectedId = $derived(stacks.selected[0]?.stack_id ?? null);

  // Uniform progressFraction for every stack — completed/skipped → 1, failed/acquiring → partial,
  // planned → 0. No template branches; CSS renders the same markup for every status.
  function progressFraction(stack: Stack): number {
    if (stack.status === 'completed' || stack.status === 'skipped') return 1;
    if (stack.status === 'acquiring' || stack.status === 'failed') {
      return Math.min(1, acquisition.framesCaptured(stack.stack_id) / stack.num_frames);
    }
    return 0;
  }

  function tooltipText(stack: Stack, index: number): string {
    const captured = acquisition.framesCaptured(stack.stack_id);
    const total = stack.num_frames;
    const progress = stack.status === 'completed' ? total : captured;
    const lines = [`#${index + 1} ${stack.profile_id}`, `${stack.status} · ${progress}/${total} frames`];
    const p = acquisition.progressByStack.get(stack.stack_id);
    if (p?.error_message) lines.push(`error: ${p.error_message}`);
    return lines.join('\n');
  }

  const stats = $derived.by(() => {
    let totalFrames = 0;
    let capturedFrames = 0;
    let totalBatchS = 0;
    let totalBatchFrames = 0;
    let completedCount = 0;
    let failedCount = 0;
    for (const s of list) {
      totalFrames += s.num_frames;
      if (s.status === 'completed') {
        capturedFrames += s.num_frames;
        completedCount += 1;
      } else if (s.status === 'failed') {
        capturedFrames += acquisition.framesCaptured(s.stack_id);
        failedCount += 1;
      } else if (s.status === 'acquiring') {
        capturedFrames += acquisition.framesCaptured(s.stack_id);
      }
      const p = acquisition.progressByStack.get(s.stack_id);
      if (!p) continue;
      for (const batches of Object.values(p.channels)) {
        for (const b of batches) {
          totalBatchS += b.duration_s;
          totalBatchFrames += b.num_frames;
        }
      }
    }
    const remainingFrames = Math.max(0, totalFrames - capturedFrames);
    const avgPerFrameS = totalBatchFrames > 0 ? totalBatchS / totalBatchFrames : null;
    const etaS = avgPerFrameS !== null && remainingFrames > 0 ? avgPerFrameS * remainingFrames : null;
    return {
      totalFrames,
      capturedFrames,
      remainingFrames,
      etaS,
      completedCount,
      failedCount,
      totalStacks: list.length
    };
  });

  function formatEta(seconds: number): string {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) {
      const m = Math.floor(seconds / 60);
      const s = Math.round(seconds % 60);
      return s > 0 ? `${m}m ${s}s` : `${m}m`;
    }
    const h = Math.floor(seconds / 3600);
    const m = Math.round((seconds % 3600) / 60);
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
  }

  let gridEl = $state<HTMLDivElement | null>(null);

  function focusCell(stackId: string) {
    gridEl?.querySelector<HTMLButtonElement>(`[data-stack-id="${stackId}"]`)?.focus();
  }

  function onKeyDown(e: KeyboardEvent) {
    if (list.length === 0) return;
    const currentIdx = selectedId ? list.findIndex((s) => s.stack_id === selectedId) : -1;
    let targetIdx: number | null = null;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') targetIdx = Math.max(0, (currentIdx < 0 ? 0 : currentIdx) - 1);
    else if (e.key === 'ArrowRight' || e.key === 'ArrowDown')
      targetIdx = Math.min(list.length - 1, (currentIdx < 0 ? -1 : currentIdx) + 1);
    else if (e.key === 'Home') targetIdx = 0;
    else if (e.key === 'End') targetIdx = list.length - 1;
    if (targetIdx !== null && targetIdx !== currentIdx) {
      e.preventDefault();
      const target = list[targetIdx];
      stacks.select([target]);
      queueMicrotask(() => focusCell(target.stack_id));
    }
  }
</script>

{#if list.length > 0}
  <div class="flex flex-col gap-4 {className}">
    <div
      bind:this={gridEl}
      class="progress-grid"
      onkeydown={onKeyDown}
      role="toolbar"
      aria-orientation="horizontal"
      aria-label="Stack progress"
      tabindex="-1"
    >
      {#each list as stack, i (stack.stack_id)}
        <button
          type="button"
          data-stack-id={stack.stack_id}
          data-stack-status={stack.status}
          aria-current={stack.stack_id === selectedId ? 'true' : undefined}
          aria-label={tooltipText(stack, i)}
          title={tooltipText(stack, i)}
          tabindex={stack.stack_id === selectedId ? 0 : -1}
          style:--progress="{progressFraction(stack) * 100}%"
          style:--weight={stack.num_frames}
          style:--min-basis="{(100 / Math.max(list.length, 1)).toFixed(2)}%"
          class="progress-cell"
          onclick={() => stacks.select([stack])}
        >
          <span class="cell-fill"></span>
        </button>
      {/each}
    </div>
    <div class="flex items-center justify-between text-xs text-fg-muted tabular-nums">
      <span>
        {stats.capturedFrames.toLocaleString()}/{stats.totalFrames.toLocaleString()} frames · {stats.completedCount}/{stats.totalStacks}
        stacks{stats.failedCount > 0 ? ` · ${stats.failedCount} failed` : ''}
      </span>
      <span class="text-fg-faint">
        {stats.etaS !== null ? `~${formatEta(stats.etaS)} remaining` : ''}
      </span>
    </div>
  </div>
{/if}

<style>
  .progress-grid {
    display: flex;
    gap: 2px;
    --_weight-sum: 1;
  }

  .progress-cell {
    position: relative;
    height: 1.25rem;
    overflow: hidden;
    border-radius: 2px;
    background: var(--color-border);
    cursor: pointer;
    flex-grow: var(--weight, 1);
    flex-shrink: 1;
    flex-basis: var(--min-basis, 0.75rem);
    min-width: 0.6rem;
    padding: 0;
    border: 0;
    outline: 1px solid transparent;
    outline-offset: 1px;
    transition: outline-color 0.15s ease;
  }

  .progress-cell[aria-current='true'] {
    outline-color: var(--color-fg-faint);
  }

  .progress-cell:focus-visible {
    outline-color: var(--color-fg-faint);
  }

  .cell-fill {
    position: absolute;
    inset: 0;
    width: var(--progress, 0%);
    background: var(--stack-status);
    transition: width 0.3s ease;
    pointer-events: none;
  }

  /* Shimmer overlay only on the actively acquiring cell. Pure CSS, no markup branches. */
  .progress-cell[data-stack-status='acquiring'] .cell-fill::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(
      90deg,
      transparent 0%,
      color-mix(in srgb, white 30%, transparent) 50%,
      transparent 100%
    );
    animation: shimmer 1.6s infinite;
  }

  @keyframes shimmer {
    0% {
      transform: translateX(-100%);
    }
    100% {
      transform: translateX(100%);
    }
  }
</style>
