<script module lang="ts">
  import type { LogEntry } from '$lib/core/model';
  import { prefs } from '$lib/core/prefs';

  type Level = 'debug' | 'info' | 'warning' | 'error';
  // Ordered by severity; the filter shows the chosen level and everything above it.
  const LEVELS: Level[] = ['debug', 'info', 'warning', 'error'];
  const LEVEL_VALUES: Record<Level, number> = { debug: 10, info: 20, warning: 30, error: 40 };

  const minLevel = prefs.logs.minLevel;
  const wrap = prefs.logs.wrap;

  /** Where the shown lines come from: 1 device, 1 node, or all. */
  type Source = 'all' | `device:${string}` | `node:${string}`;
  let source = $state<Source>('all');

  /** Shows only the lines of a device or a node. "Show in logs" in the Issues tab uses it. */
  export function showLogsOf(from: { device?: string; node?: string }): void {
    source = from.device ? `device:${from.device}` : from.node ? `node:${from.node}` : 'all';
  }

  /** The device of a log line: the first part of its logger name, when that part is a device. */
  function logDevice(log: LogEntry, devices: readonly string[]): string | null {
    const head = log.logger.split('.')[0];
    return devices.includes(head) ? head : null;
  }
</script>

<script lang="ts">
  import type { Component } from 'svelte';

  import { Button, Select, TextBox } from '@voxel/kit';
  import { cn } from '@voxel/kit/cn';
  import { displayName } from '@voxel/kit/format';
  import { Bug, ChevronDown, ChevronUp, CircleAlert, Dot, Info, TriangleAlert, WrapText } from '@voxel/kit/icons';

  interface Props {
    logs: LogEntry[];
    /** The devices of the open instrument, for the Source filter. */
    devices?: readonly string[];
    expanded?: boolean;
    ontoggle?: () => void;
    showFooter?: boolean;
    class?: string;
  }

  const { logs, devices = [], expanded = true, ontoggle, showFooter = true, class: className }: Props = $props();

  let query = $state('');
  // The picked source stays in the list, also when it has no lines yet.
  const sources = $derived<Source[]>([
    ...new Set<Source>([
      'all',
      ...[...devices].sort().map((id) => `device:${id}` as const),
      ...logs.flatMap((log) => (log.node_id ? [`node:${log.node_id}` as const] : [])).sort(),
      source
    ])
  ]);
  const filtered = $derived.by(() => {
    const min = LEVEL_VALUES[minLevel.get()];
    const text = query.trim().toLowerCase();
    const [kind, id] = source === 'all' ? [] : source.split(/:(.*)/);
    return logs.filter(
      (log) =>
        log.level >= min &&
        (kind !== 'device' || logDevice(log, devices) === id) &&
        (kind !== 'node' || log.node_id === id) &&
        (!text ||
          [log.message, log.logger, log.exception?.kind, log.exception?.message].some((part) =>
            part?.toLowerCase().includes(text)
          ))
    );
  });
  const warnings = $derived(logs.filter((log) => log.level >= 30 && log.level < 40).length);
  const errors = $derived(logs.filter((log) => log.level >= 40).length);

  let container = $state<HTMLDivElement>();

  // Auto-scroll to bottom when new (visible) logs arrive
  $effect(() => {
    if (container && filtered.length > 0) {
      container.scrollTop = container.scrollHeight;
    }
  });

  function levelName(level: number): Level {
    if (level >= 40) return 'error';
    if (level >= 30) return 'warning';
    if (level >= 20) return 'info';
    return 'debug';
  }

  function getLevelColor(level: number): string {
    switch (levelName(level)) {
      case 'debug':
        return 'text-fg-muted';
      case 'info':
        return 'text-fg';
      case 'warning':
        return 'text-warning-fg';
      case 'error':
        return 'text-danger-fg';
      default:
        return 'text-fg-muted';
    }
  }

  const levelIcons: Record<string, Component> = {
    debug: Bug,
    info: Info,
    warning: TriangleAlert,
    error: CircleAlert
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

  function sourceLabel(value: Source): string {
    return value === 'all' ? 'All' : displayName(value.slice(value.indexOf(':') + 1));
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
    <span class="text-danger-fg">{errors} {errors === 1 ? 'error' : 'errors'}</span>
  {/if}
  {#if warnings > 0}
    <span class="text-warning-fg">{warnings} {warnings === 1 ? 'warning' : 'warnings'}</span>
  {/if}
{/snippet}

<div class={cn('flex h-full min-h-0 flex-col overflow-hidden', className)}>
  {#if expanded}
    <div class="bottom-panel-bar">
      <Select
        class="max-h-6 w-56"
        value={source}
        options={sources}
        formatLabel={sourceLabel}
        onChange={(value) => (source = value)}
        prefix="Source"
      />
      <Select
        variant="filled"
        class="max-h-6 w-36"
        value={minLevel.get()}
        options={LEVELS}
        formatLabel={displayName}
        onChange={(level) => minLevel.set(level)}
        prefix="Level ≥"
      />
      <TextBox
        live
        class="ml-auto w-64"
        value={query}
        onChange={(text) => (query = text)}
        placeholder="Search"
        aria-label="Search logs"
      />
      <Button
        variant={wrap.get() ? 'ghost' : 'secondary'}
        aria-pressed={wrap.get()}
        onclick={() => wrap.set(!wrap.get())}
      >
        <WrapText width="14" height="14" />Wrap
      </Button>
    </div>

    <div bind:this={container} class="log-container bottom-panel-box font-mono">
      {#if filtered.length === 0}
        <div class="flex h-full items-center justify-center text-fg-muted">
          {logs.length === 0 ? 'Waiting for logs...' : 'No logs match the current filter'}
        </div>
      {:else}
        <div class="space-y-0.5 p-2">
          {#each filtered as log (log.seq)}
            {@const name = levelName(log.level)}
            {@const LevelIcon = levelIcons[name] ?? Dot}
            <div class="flex gap-2 {wrap.get() ? 'items-start' : 'items-center'}">
              <span class="w-[8ch] shrink-0 text-fg-muted">{formatTime(log.emitted_at)}</span>
              <span class="min-w-0 flex-1 {wrap.get() ? 'wrap-break-word' : 'truncate'}">
                <span class="mr-2 {getLevelColor(log.level)}" title={log.logger}>
                  {truncateMiddle(log.logger, 42)}
                </span>
                <span class="text-fg">{log.message}</span>
                {#if log.node_id}<span class="ml-2 text-fg-muted">[{log.node_id}]</span>{/if}
              </span>
              <span class="shrink-0 {getLevelColor(log.level)}" title={name}>
                <LevelIcon width="14" height="14" />
              </span>
            </div>
            <!-- The cause of the error, under the message. A click shows where in the code it came from. -->
            {#if log.exception}
              {@const { kind, message, traceback, truncated } = log.exception}
              <details class="ml-[calc(8ch+(--spacing(2)))]">
                <summary
                  class="cursor-pointer {getLevelColor(log.level)} {wrap.get() ? 'wrap-break-word' : 'truncate'}"
                >
                  {message ? `${kind}: ${message}` : kind}
                </summary>
                <pre class="overflow-x-auto py-1 whitespace-pre text-fg-muted">{traceback}{truncated ? '\n…' : ''}</pre>
              </details>
            {/if}
          {/each}
        </div>
      {/if}
    </div>
  {/if}

  {#if showFooter}
    <footer class="flex h-7 shrink-0 items-center border-t border-line-muted bg-shell text-base">
      {#if ontoggle}
        <button
          type="button"
          aria-expanded={expanded}
          onclick={ontoggle}
          class="flex h-full min-w-0 flex-1 cursor-pointer items-center gap-3 px-3 text-fg-muted transition-colors hover:text-fg"
        >
          {@render summary()}
          <span class="ml-auto flex items-center gap-1.5">
            {expanded ? 'Collapse' : 'Expand'}
            {#if expanded}
              <ChevronDown width="14" height="14" />
            {:else}
              <ChevronUp width="14" height="14" />
            {/if}
          </span>
        </button>
      {:else}
        <div class="flex h-full min-w-0 flex-1 items-center gap-3 px-3">
          {@render summary()}
        </div>
      {/if}
    </footer>
  {/if}
</div>

<style>
  .log-container {
    scrollbar-width: thin;
    scrollbar-color: var(--scrollbar-thumb) transparent;
  }

  .log-container::-webkit-scrollbar {
    width: 6px;
  }

  .log-container::-webkit-scrollbar-track {
    background: transparent;
  }

  .log-container::-webkit-scrollbar-thumb {
    background-color: var(--scrollbar-thumb);
    border-radius: 3px;
  }

  .log-container::-webkit-scrollbar-thumb:hover {
    background-color: var(--scrollbar-thumb-hover);
  }
</style>
