<script lang="ts">
  import DiffJsonView from './DiffJsonView.svelte';

  interface Props {
    data: unknown;
    base?: unknown;
    expandDepth?: number;
    /** @internal current recursion depth */
    depth?: number;
  }

  let { data, base = undefined, expandDepth = 1, depth = 0 }: Props = $props();

  type Entry = { key: string; value: unknown; base: unknown };

  function childBase(b: unknown, key: string): unknown {
    return b != null && typeof b === 'object' ? (b as Record<string, unknown>)[key] : undefined;
  }

  let entries: Entry[] = $derived.by(() => {
    if (data == null || typeof data !== 'object') return [];
    const source = Array.isArray(data)
      ? data.map((v, i) => [String(i), v] as const)
      : Object.entries(data as Record<string, unknown>);
    return source.map(([k, v]) => ({ key: k, value: v, base: childBase(base, k) }));
  });

  function isContainer(value: unknown): value is Record<string, unknown> | unknown[] {
    return value != null && typeof value === 'object';
  }

  function summary(value: unknown): string {
    if (Array.isArray(value)) return `[${value.length}]`;
    if (typeof value === 'object' && value !== null) return `{${Object.keys(value).length}}`;
    return '';
  }

  function formatNumber(value: number): string {
    if (Number.isInteger(value)) return String(value);
    return value.toPrecision(6).replace(/\.?0+$/, '');
  }

  function primitiveClass(value: unknown): string {
    if (value === null || value === undefined) return 'text-fg-faint';
    if (typeof value === 'boolean') return value ? 'text-success' : 'text-danger';
    if (typeof value === 'number') return 'text-warning';
    if (typeof value === 'string') return 'text-info';
    return 'text-fg';
  }

  function primitiveText(value: unknown): string {
    if (value === null || value === undefined) return 'null';
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    if (typeof value === 'number') return formatNumber(value);
    return String(value);
  }

  function diverged(value: unknown, b: unknown): boolean {
    return b !== undefined && JSON.stringify(value) !== JSON.stringify(b);
  }

  function containsDivergence(value: unknown, b: unknown): boolean {
    if (isContainer(value) && isContainer(b)) {
      const keys = Array.isArray(value)
        ? value.map((_, i) => String(i))
        : Object.keys(value as Record<string, unknown>);
      return keys.some((k) => containsDivergence((value as Record<string, unknown>)[k], childBase(b, k)));
    }
    return diverged(value, b);
  }
</script>

{#if entries.length > 0}
  <div class="space-y-px">
    {#each entries as { key, value, base: b } (key)}
      {#if isContainer(value)}
        <details open={depth < expandDepth}>
          <summary
            class="flex cursor-pointer list-none items-center gap-1.5 rounded px-1 py-0.5 select-none [&::-webkit-details-marker]:hidden {containsDivergence(
              value,
              b
            )
              ? 'bg-warning/10 [[open]>&]:bg-transparent'
              : ''}"
          >
            <svg
              class="h-3 w-3 shrink-0 text-fg-muted/60 transition-transform [[open]>summary>&]:rotate-90"
              viewBox="0 0 16 16"
              fill="currentColor"
            >
              <path d="M6 4l4 4-4 4z" />
            </svg>
            <span class="text-fg-muted">{key}:</span>
            <span class="text-base text-fg-faint">{summary(value)}</span>
          </summary>
          <div class="ml-2 border-l border-border/50 pl-2">
            <DiffJsonView data={value} base={b} depth={depth + 1} {expandDepth} />
          </div>
        </details>
      {:else}
        <div class="flex items-baseline flex-wrap gap-2 rounded px-1 py-0.5 {diverged(value, b) ? 'bg-warning/10' : ''}">
          <span class="shrink-0 text-fg-muted">{key}:</span>
          <span class="font-mono {primitiveClass(value)}">{primitiveText(value)}</span>
          {#if diverged(value, b)}
            <span class="font-mono text-fg-muted ml-auto">({primitiveText(b)})</span>
          {/if}
        </div>
      {/if}
    {/each}
  </div>
{:else if data != null && typeof data !== 'object'}
  <span class="font-mono text-lg {primitiveClass(data)}">{primitiveText(data)}</span>
{/if}
