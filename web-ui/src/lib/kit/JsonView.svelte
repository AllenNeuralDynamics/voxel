<script lang="ts">
  import { SvelteMap } from 'svelte/reactivity';

  import { cn } from '$lib/utils';

  import JsonView from './JsonView.svelte';

  interface Props {
    data: unknown;
    baseline?: unknown;
    expandDepth?: number;
    /** Resolved URLs for primitive values, keyed by JSON Pointer relative to data (e.g. /channels/0). */
    links?: Readonly<Record<string, string>>;
    /** @internal whether this branch belongs to a comparison */
    comparing?: boolean;
    /** @internal current recursion depth */
    depth?: number;
    /** @internal JSON Pointer of this recursive branch */
    path?: string;
  }

  let {
    data,
    baseline = undefined,
    expandDepth = 1,
    links = {},
    comparing = baseline !== undefined,
    depth = 0,
    path = ''
  }: Props = $props();
  const expanded = new SvelteMap<string, boolean>();

  type Entry = { key: string; value: unknown; baseline: unknown };

  function childValue(value: unknown, key: string): unknown {
    return value != null && typeof value === 'object' ? (value as Record<string, unknown>)[key] : undefined;
  }

  let entries: Entry[] = $derived.by(() => {
    if (data == null || typeof data !== 'object') return [];
    const source = Array.isArray(data)
      ? data.map((value, index) => [String(index), value] as const)
      : Object.entries(data as Record<string, unknown>);
    return source.map(([key, value]) => ({
      key,
      value,
      baseline: childValue(baseline, key)
    }));
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

  function primitiveLayoutClass(value: unknown): string {
    return typeof value === 'string'
      ? 'min-w-0 wrap-anywhere @max-[14rem]/json-row:ml-4 @max-[14rem]/json-row:basis-[calc(100%-1rem)]'
      : 'shrink-0 whitespace-nowrap';
  }

  function primitiveText(value: unknown): string {
    if (value === null) return 'null';
    if (value === undefined) return 'missing';
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    if (typeof value === 'number') return formatNumber(value);
    return String(value);
  }

  function equal(left: unknown, right: unknown): boolean {
    if (Object.is(left, right)) return true;
    if (!isContainer(left) || !isContainer(right)) return false;
    if (Array.isArray(left) !== Array.isArray(right)) return false;

    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    return (
      leftKeys.length === rightKeys.length &&
      leftKeys.every((key) => Object.hasOwn(right, key) && equal(childValue(left, key), childValue(right, key)))
    );
  }

  function diverged(value: unknown, baselineValue: unknown): boolean {
    return comparing && !equal(value, baselineValue);
  }
</script>

{#snippet primitive(value: unknown, pointer: string, large = false)}
  {@const href = Object.hasOwn(links, pointer) ? links[pointer] : undefined}
  {#if href}
    <!-- eslint-disable svelte/no-navigation-without-resolve -- The caller supplies already-resolved URLs. -->
    <a
      {href}
      class={cn(
        'font-mono underline underline-offset-2 hover:decoration-current focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focused',
        primitiveClass(value),
        primitiveLayoutClass(value),
        large && 'text-lg'
      )}>{primitiveText(value)}</a
    >
    <!-- eslint-enable svelte/no-navigation-without-resolve -->
  {:else}
    <span class={cn('font-mono', primitiveClass(value), primitiveLayoutClass(value), large && 'text-lg')}
      >{primitiveText(value)}</span
    >
  {/if}
{/snippet}

{#if entries.length > 0}
  {@const rowStyle = '@container/json-row flex min-w-0 flex-wrap items-start gap-2 px-0 py-0.5'}
  {@const caretSize = 'h-4 w-4 -mx-1'}
  <div class="min-w-0 space-y-px">
    {#each entries as { key, value, baseline: baselineValue } (key)}
      {@const entryPath = `${path}/${key.replace(/~/g, '~0').replace(/\//g, '~1')}`}
      {#if isContainer(value)}
        <details
          class="min-w-0"
          open={expanded.get(key) ?? depth < expandDepth}
          ontoggle={(event) => expanded.set(key, event.currentTarget.open)}
        >
          <summary
            class={cn(
              rowStyle,
              'cursor-pointer list-none rounded select-none [&::-webkit-details-marker]:hidden',
              diverged(value, baselineValue) ? 'bg-warning/10 [[open]>&]:bg-transparent' : ''
            )}
          >
            <svg
              class={cn(caretSize, 'text-fg-muted/60 transition-transform [[open]>summary>&]:rotate-90')}
              viewBox="0 0 16 16"
              fill="currentColor"
            >
              <path d="M6 4l4 4-4 4z" />
            </svg>
            <span class="text-fg-muted">{key}:</span>
            <span class="text-base text-fg-faint">{summary(value)}</span>
          </summary>
          <div class="ml-2 min-w-0 border-l border-border/50 pl-2">
            <JsonView
              data={value}
              baseline={baselineValue}
              {comparing}
              depth={depth + 1}
              {expandDepth}
              {links}
              path={entryPath}
            />
          </div>
        </details>
      {:else}
        <div class={cn(rowStyle, 'rounded', diverged(value, baselineValue) ? 'bg-warning/10' : '')}>
          <span aria-hidden="true" class={cn(caretSize, 'shrink-0')}></span>
          <span class="shrink-0 text-fg-muted">{key}:</span>
          {@render primitive(value, entryPath)}
          {#if diverged(value, baselineValue)}
            <span
              class={cn(
                'ml-auto font-mono text-fg-muted @max-[14rem]/json-row:ml-4 @max-[14rem]/json-row:basis-[calc(100%-1rem)]',
                primitiveLayoutClass(baselineValue)
              )}>({primitiveText(baselineValue)})</span
            >
          {/if}
        </div>
      {/if}
    {/each}
  </div>
{:else if data != null && typeof data !== 'object'}
  <div class={cn('flex min-w-0 flex-wrap items-start rounded', diverged(data, baseline) ? 'bg-warning/10' : '')}>
    {@render primitive(data, path, true)}
    {#if diverged(data, baseline)}
      <span
        class={cn(
          'ml-auto font-mono text-fg-muted @max-[14rem]/json-row:ml-4 @max-[14rem]/json-row:basis-[calc(100%-1rem)]',
          primitiveLayoutClass(baseline)
        )}>({primitiveText(baseline)})</span
      >
    {/if}
  </div>
{/if}
