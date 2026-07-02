<script module lang="ts">
  import { browser } from '$app/environment';
  import type { LogMessage } from '$lib/model';

  type Level = LogMessage['level'];
  // Ordered by severity; the filter shows the chosen level and everything above it.
  const LEVELS: Level[] = ['debug', 'info', 'warning', 'error'];
  const LEVEL_OPTIONS = LEVELS.map((l) => ({ value: l, label: l[0].toUpperCase() + l.slice(1) }));

  function loadPref<T>(key: string, fallback: T): T {
    if (!browser) return fallback;
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? fallback : (JSON.parse(raw) as T);
    } catch {
      return fallback;
    }
  }

  // View prefs shared across every LogViewer instance (launch screen ↔ session shell) and persisted to
  // localStorage. `minLevel` is the lowest severity shown — the server streams DEBUG too, revealed when lowered.
  const view = $state<{ minLevel: Level; wrap: boolean }>({
    minLevel: loadPref<Level>('logviewer.minLevel', 'info'),
    wrap: loadPref<boolean>('logviewer.wrap', false)
  });

  if (browser) {
    $effect.root(() => {
      $effect(() => localStorage.setItem('logviewer.minLevel', JSON.stringify(view.minLevel)));
      $effect(() => localStorage.setItem('logviewer.wrap', JSON.stringify(view.wrap)));
    });
  }
</script>

<script lang="ts">
  import type { Component } from 'svelte';

  import { AlertCircleOutline, AlertOutline, BugOutline, CircleSmall, InformationOutline } from '$lib/icons';
  import { Checkbox, Select } from '$lib/kit';
  import { cn } from '$lib/utils';

  const { logs, class: className }: { logs: LogMessage[]; class?: string } = $props();

  const filtered = $derived(logs.filter((log) => LEVELS.indexOf(log.level) >= LEVELS.indexOf(view.minLevel)));

  let container: HTMLDivElement;

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

<div class={cn('flex h-full flex-col gap-0 overflow-hidden p-4 pt-0', className)}>
  <div class="flex shrink-0 items-center gap-2 py-2">
    <div class="flex items-center gap-3">
      <label
        class="flex cursor-pointer items-center gap-1.5 text-xs transition-colors {view.wrap
          ? 'text-fg'
          : 'text-fg-muted'} hover:text-fg"
      >
        <Checkbox size="xs" bind:checked={view.wrap} />
        Wrap
      </label>
    </div>
    <!-- variant="ghost" -->
    <div class="ml-auto">
      <Select
        size="xs"
        class="ml-auto border-transparent hover:border-accent"
        value={view.minLevel}
        options={LEVEL_OPTIONS}
        onchange={(v) => (view.minLevel = v as Level)}
        prefix="Level ≥"
      />
    </div>
  </div>
  <div
    bind:this={container}
    class="log-container min-h-0 flex-1 overflow-y-auto rounded border border-border bg-canvas font-mono text-sm"
  >
    {#if filtered.length === 0}
      <div class="flex h-full items-center justify-center text-fg-muted">
        {logs.length === 0 ? 'Waiting for logs...' : 'No logs match the current filter'}
      </div>
    {:else}
      <div class="space-y-0.5 p-2">
        {#each filtered as log, i (i)}
          {@const LevelIcon = levelIcons[log.level] ?? CircleSmall}
          <div class="flex gap-2 {view.wrap ? 'items-start' : 'items-center'}">
            <span class="w-[8ch] shrink-0 text-fg-muted/65">{formatTime(log.timestamp)}</span>
            <span class="min-w-0 flex-1 {view.wrap ? 'wrap-break-word' : 'truncate'}">
              <span class="mr-2 {getLevelColor(log.level)}" title={log.logger}>{truncateMiddle(log.logger, 42)}</span>
              <span class="text-fg/80">{log.message}</span>
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
