<script module lang="ts">
  import type { LogMessage } from '$lib/model';
  import { pref } from '$lib/utils';

  type Level = LogMessage['level'];
  // Ordered by severity; the filter shows the chosen level and everything above it.
  const LEVELS: Level[] = ['debug', 'info', 'warning', 'error'];
  const LEVEL_OPTIONS = LEVELS.map((l) => ({ value: l, label: l[0].toUpperCase() + l.slice(1) }));

  const minLevel = pref<Level>('log:min-level', 'info');
  const wrap = pref('log:wrap', false);
</script>

<script lang="ts">
  import type { Component } from 'svelte';

  import {
    AlertCircleOutline,
    AlertOutline,
    BugOutline,
    ChevronDown,
    ChevronUp,
    CircleSmall,
    InformationOutline,
    WrapText
  } from '$lib/icons';
  import { Select } from '$lib/kit';
  import { cn } from '$lib/utils';

  interface Props {
    logs: LogMessage[];
    expanded?: boolean;
    ontoggle?: () => void;
    class?: string;
  }

  const { logs, expanded = true, ontoggle, class: className }: Props = $props();

  const filtered = $derived(logs.filter((log) => LEVELS.indexOf(log.level) >= LEVELS.indexOf(minLevel.get())));
  const warnings = $derived(logs.filter((log) => log.level === 'warning').length);
  const errors = $derived(logs.filter((log) => log.level === 'error').length);

  let container = $state<HTMLDivElement>();

  // Auto-scroll to bottom when new (visible) logs arrive
  $effect(() => {
    if (container && filtered.length > 0) {
      container.scrollTop = container.scrollHeight;
    }
  });

  function getLevelColor(level: LogMessage['level']): string {
    switch (level) {
      case 'debug':
        return 'text-fg-muted';
      case 'info':
        return 'text-info';
      case 'warning':
        return 'text-warning';
      case 'error':
        return 'text-danger';
      default:
        return 'text-fg-muted';
    }
  }

  const levelIcons: Record<string, Component> = {
    debug: BugOutline,
    info: InformationOutline,
    warning: AlertOutline,
    error: AlertCircleOutline
  };

  function formatTime(timestamp: string): string {
    const date = new Date(timestamp);
    return date.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  }

  function truncateMiddle(str: string, maxLen: number): string {
    if (str.length <= maxLen) return str;
    const half = Math.floor((maxLen - 1) / 2);
    return str.slice(0, half) + '…' + str.slice(-(maxLen - half - 1));
  }
</script>

{#snippet summary()}
  <span class="font-medium text-fg">Logs</span>
  {#if errors > 0}
    <span class="text-danger">{errors} {errors === 1 ? 'error' : 'errors'}</span>
  {/if}
  {#if warnings > 0}
    <span class="text-warning">{warnings} {warnings === 1 ? 'warning' : 'warnings'}</span>
  {/if}
{/snippet}

<div class={cn('flex h-full min-h-0 flex-col overflow-hidden', className)}>
  {#if expanded}
    <div class="min-h-0 flex-1 overflow-hidden p-2">
      <div
        bind:this={container}
        class="log-container h-full overflow-y-auto rounded-sm border border-border bg-canvas font-mono text-sm"
      >
        {#if filtered.length === 0}
          <div class="flex h-full items-center justify-center text-fg-muted">
            {logs.length === 0 ? 'Waiting for logs...' : 'No logs match the current filter'}
          </div>
        {:else}
          <div class="space-y-0.5 p-2">
            {#each filtered as log, i (i)}
              {@const LevelIcon = levelIcons[log.level] ?? CircleSmall}
              <div class="flex gap-2 {wrap.get() ? 'items-start' : 'items-center'}">
                <span class="w-[8ch] shrink-0 text-fg-muted">{formatTime(log.timestamp)}</span>
                <span class="min-w-0 flex-1 {wrap.get() ? 'wrap-break-word' : 'truncate'}">
                  <span class="mr-2 {getLevelColor(log.level)}" title={log.logger}>
                    {truncateMiddle(log.logger, 42)}
                  </span>
                  <span class="text-fg">{log.message}</span>
                </span>
                <span class="shrink-0 {getLevelColor(log.level)}" title={log.level}>
                  <LevelIcon width="14" height="14" />
                </span>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </div>
  {/if}

  <footer class="flex h-7 shrink-0 items-center border-t border-border bg-elevated text-base">
    {#if ontoggle}
      <button
        type="button"
        aria-expanded={expanded}
        onclick={ontoggle}
        class="flex h-full min-w-0 flex-1 cursor-pointer items-center gap-3 px-3 text-fg-muted transition-colors hover:text-fg"
      >
        {@render summary()}
      </button>
    {:else}
      <div class="flex h-full min-w-0 flex-1 items-center gap-3 px-3">
        {@render summary()}
      </div>
    {/if}

    <button
      type="button"
      aria-pressed={wrap.get()}
      onclick={() => wrap.set(!wrap.get())}
      class={cn(
        'mx-1 flex h-full cursor-pointer items-center gap-1.5 rounded border px-2 transition-colors',
        wrap.get()
          ? 'border-border bg-element-selected text-fg shadow-sm'
          : 'border-transparent text-fg-muted hover:text-fg'
      )}
    >
      <WrapText width="14" height="14" />
      Wrap
    </button>

    <Select
      size="xs"
      class="mx-2 w-30 border-transparent bg-transparent hover:bg-element-hover"
      value={minLevel.get()}
      options={LEVEL_OPTIONS}
      onchange={(value) => minLevel.set(value as Level)}
      prefix="Level ≥"
    />

    {#if ontoggle}
      <button
        type="button"
        aria-expanded={expanded}
        onclick={ontoggle}
        class="flex h-full min-w-26 cursor-pointer items-center justify-end gap-1.5 px-3 text-fg-muted transition-colors hover:text-fg"
      >
        {expanded ? 'Collapse' : 'Expand'}
        {#if expanded}
          <ChevronDown width="14" height="14" />
        {:else}
          <ChevronUp width="14" height="14" />
        {/if}
      </button>
    {/if}
  </footer>
</div>

<style>
  .log-container {
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
  }

  .log-container::-webkit-scrollbar {
    width: 6px;
  }

  .log-container::-webkit-scrollbar-track {
    background: transparent;
  }

  .log-container::-webkit-scrollbar-thumb {
    background-color: var(--border);
    border-radius: 3px;
  }

  .log-container::-webkit-scrollbar-thumb:hover {
    background-color: var(--fg-muted);
  }
</style>
