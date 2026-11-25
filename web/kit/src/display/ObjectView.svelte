<script lang="ts" module>
  import type { Snippet } from 'svelte';

  /**
   * Something that a page puts on 1 row of an `ObjectView`: `content`, at the row that `path` leads to. A path is
   * the keys from the top, with the place of an item in a list as a number. `content` gets `data`, which is what
   * the page wants to show there, such as a message.
   */
  export interface ObjectMark {
    path: (string | number)[];
    content: Snippet<[data: unknown]>;
    data?: unknown;
  }
</script>

<script lang="ts">
  import { SvelteMap, SvelteSet } from 'svelte/reactivity';

  import { ChevronRight } from '../icons';
  import { cn } from '../utils/cn';
  import { ObjectDiff } from '../utils/object-diff';

  interface Props {
    /** The data to show: plain values, and lists and maps of them. */
    data: unknown;
    /** What `data` is compared with. A value of it that `data` does not have shows as removed, and a value of `data`
     * that it does not have as added. */
    baseline?: unknown;
    /** With a `baseline`: leaves out what is the same, and keeps each change and the keys it is under. A row stands
     * for what a list or a map leaves out, and shows it when pressed. */
    changesOnly?: boolean;
    /** How many levels start open. A list or a map deeper than this starts folded. */
    expandDepth?: number;
    /** Marks that each draw as a new row under their row, across the width. A row with one always shows, also with
     * `changesOnly`, and a folded row that hides one has a line at its right edge. */
    blockMarks?: ObjectMark[];
    /** Marks that each draw at the end of their row. They show and hide as `blockMarks` do. */
    inlineMarks?: ObjectMark[];
    class?: string;
  }

  let {
    data,
    baseline = undefined,
    changesOnly = false,
    expandDepth = Infinity,
    blockMarks = [],
    inlineMarks = [],
    class: className = ''
  }: Props = $props();

  type Change = 'same' | 'removed' | 'added';

  /** 1 row: a key that opens a list or a map, a key with its plain value, or the count of what is left out. */
  type Line =
    | {
        kind: 'open';
        path: string;
        keys: string[];
        depth: number;
        label: string;
        change: Change;
        folded: boolean;
        size: number;
        hides: boolean;
        hidesMark: boolean;
        marks: boolean;
      }
    | {
        kind: 'value';
        path: string;
        keys: string[];
        depth: number;
        label: string;
        change: Change;
        value: unknown;
        marks: boolean;
      }
    | { kind: 'more'; path: string; depth: number; count: number };

  // What a person folded or opened, by path, and the lists and maps whose left-out rows a person asked for.
  const folds = new SvelteMap<string, boolean>();
  const shown = new SvelteSet<string>();

  const comparing = $derived(baseline !== undefined);

  // The marks by the row they are on, and every path that has a mark.
  const blockAt = $derived(Map.groupBy(blockMarks, (mark) => JSON.stringify(mark.path.map(String))));
  const inlineAt = $derived(Map.groupBy(inlineMarks, (mark) => JSON.stringify(mark.path.map(String))));
  const marked = $derived([...blockMarks, ...inlineMarks].map((mark) => mark.path.map(String)));

  /** Whether a mark is on the row at `keys`, or on a row under it; with `under`, only on a row under it. */
  function holdsMark(keys: string[], under = false): boolean {
    return marked.some(
      (path) => path.length >= keys.length + (under ? 1 : 0) && keys.every((key, index) => path[index] === key)
    );
  }

  /** The rows of the items of the list or map at `path`. `side` is `removed` or `added` for a list or a map that only
   * 1 side has. */
  function inside(
    now: unknown,
    was: unknown,
    path: string,
    keys: string[],
    depth: number,
    side: Change,
    out: Line[]
  ): void {
    const list = Array.isArray(now ?? was);
    let left = 0;
    for (const key of ObjectDiff.keys(now, was)) {
      const [a, b] = [ObjectDiff.parts(now)?.[key], ObjectDiff.parts(was)?.[key]];
      const at = [...keys, key];
      if (changesOnly && comparing && side === 'same' && !shown.has(path) && ObjectDiff.same(a, b) && !holdsMark(at)) {
        left += 1;
        continue;
      }
      const label = list ? '-' : `${key}:`;
      const next = `${path}/${key}`;
      const missing =
        side !== 'same'
          ? side
          : !comparing
            ? 'same'
            : !(key in (ObjectDiff.parts(now) ?? {}))
              ? 'removed'
              : !(key in (ObjectDiff.parts(was) ?? {}))
                ? 'added'
                : 'same';
      if (missing !== 'same') {
        node(missing === 'removed' ? b : a, undefined, next, at, depth, label, missing, true, out);
      } else if ((ObjectDiff.parts(a) === undefined) !== (ObjectDiff.parts(b) === undefined) && comparing) {
        // A plain value on 1 side and a list or a map on the other: the old one goes, and the new one comes.
        node(b, undefined, next, at, depth, label, 'removed', false, out);
        node(a, undefined, next, at, depth, label, 'added', true, out);
      } else {
        node(a, b, next, at, depth, label, 'same', true, out);
      }
    }
    if (left > 0) out.push({ kind: 'more', path, depth, count: left });
  }

  /** The rows of 1 value with its key. With `side` `same`, `was` is what it is compared with. `marks` is whether the
   * marks of its path draw on it; of 2 rows for 1 key, the old value and the new one, only the new one has them. */
  function node(
    now: unknown,
    was: unknown,
    path: string,
    keys: string[],
    depth: number,
    label: string,
    side: Change,
    marks: boolean,
    out: Line[]
  ): void {
    const parts = ObjectDiff.parts(now);
    const size =
      Object.keys(parts ?? {}).length +
      (side === 'same' && comparing
        ? ObjectDiff.keys(undefined, was).filter((key) => !(key in (parts ?? {}))).length
        : 0);
    if (!parts || size === 0) {
      if (side === 'same' && comparing && !ObjectDiff.same(now, was)) {
        out.push({ kind: 'value', path: `${path}-`, keys, depth, label, change: 'removed', value: was, marks: false });
        out.push({ kind: 'value', path: `${path}+`, keys, depth, label, change: 'added', value: now, marks });
      } else {
        out.push({
          kind: 'value',
          path: `${path}${side === 'removed' ? '-' : side === 'added' ? '+' : ''}`,
          keys,
          depth,
          label,
          change: side,
          value: now,
          marks
        });
      }
      return;
    }
    const key = `${path}${side === 'removed' ? '-' : side === 'added' ? '+' : ''}`;
    const folded = folds.get(key) ?? depth >= expandDepth;
    const hides = folded && side === 'same' && comparing && !ObjectDiff.same(now, was);
    const hidesMark = folded && marks && holdsMark(keys, true);
    out.push({ kind: 'open', path: key, keys, depth, label, change: side, folded, size, hides, hidesMark, marks });
    if (!folded) inside(now, side === 'same' ? was : undefined, key, keys, depth + 1, side, out);
  }

  const lines = $derived.by(() => {
    const out: Line[] = [];
    if (
      ObjectDiff.parts(data) &&
      Object.keys(data as object).length + ObjectDiff.keys(undefined, baseline).length > 0
    ) {
      inside(data, baseline, '', [], 0, 'same', out);
    } else {
      node(data, baseline, '', [], 0, '', 'same', true, out);
    }
    return out;
  });

  /** A plain value as it is written. Text that is empty, or that would read as another kind of value, is in quotes. */
  function text(value: unknown): string {
    if (value === null || value === undefined) return 'null';
    if (Array.isArray(value)) return '[]';
    if (typeof value === 'object') return '{}';
    if (typeof value !== 'string') return String(value);
    return value === '' || /^(null|true|false|[-+]?\d+(\.\d+)?)$/.test(value.trim()) || value !== value.trim()
      ? JSON.stringify(value)
      : value;
  }

  const CHANGES: Record<Change, string> = {
    same: '',
    removed: 'bg-danger-tint text-danger-fg shadow-[inset_3px_0_var(--danger)]',
    added: 'bg-success-tint text-success-fg shadow-[inset_3px_0_var(--success)]'
  };
  const GUTTER = 'grid h-full w-7 shrink-0 place-items-center select-none';
</script>

<!-- Data as rows of text, 1 key on each row and each level a step in. The narrow part at the left of a row holds the
arrow that folds a list or a map, or the sign of a row that was removed or added. A folded row that hides a change has
a line at its left edge, and one that hides a mark has a line at its right edge. -->
<div class={cn('frame-raised py-2 font-mono text-sm/[1.7] tabular-nums', className)}>
  {#each lines as line (`${line.kind}${line.path}`)}
    {#if line.kind === 'more'}
      <div class="flex min-w-0 items-center">
        <span class={GUTTER}></span>
        <button
          type="button"
          class="cursor-pointer rounded-sm px-1.5 text-fg-muted hover:bg-element-hover hover:text-fg"
          style:margin-left="{line.depth * 2}ch"
          onclick={() => shown.add(line.path)}
        >
          ⋯ {line.count} more
        </button>
      </div>
    {:else}
      {@const changed = line.change !== 'same'}
      {@const at = JSON.stringify(line.keys)}
      <div
        class={cn(
          // The row holds text that only a screen reader gets. That text is placed from the row, so it stays in the
          // row; placed from the page, it would make the whole page taller.
          'relative flex min-w-0 items-start',
          CHANGES[line.change],
          line.kind === 'open' && line.hides && 'shadow-[inset_3px_0_var(--accent)]',
          line.kind === 'open' && line.hidesMark && 'border-r-[3px] border-fg-muted'
        )}
      >
        {#if line.kind === 'open'}
          <button
            type="button"
            class={cn(GUTTER, 'h-[1.7em] cursor-pointer text-fg-muted hover:text-fg', changed && 'text-current')}
            aria-expanded={!line.folded}
            aria-label={line.folded ? 'Unfold' : 'Fold'}
            onclick={() => folds.set(line.path, !line.folded)}
          >
            <ChevronRight class={cn('size-3.5 transition-transform', !line.folded && 'rotate-90')} aria-hidden="true" />
          </button>
        {:else}
          <span class={cn(GUTTER, 'h-[1.7em]')} aria-hidden="true">
            {line.change === 'removed' ? '−' : line.change === 'added' ? '+' : ''}
          </span>
        {/if}
        <span class="min-w-0 flex-1 pr-4 wrap-anywhere whitespace-pre-wrap" style:padding-left="{line.depth * 2}ch">
          {#if changed}<span class="sr-only">{line.change === 'removed' ? 'Removed: ' : 'Added: '}</span>{/if}
          <span class={cn(!changed && 'text-fg-muted')}>{line.label}</span>
          {#if line.kind === 'value'}
            {@const kind = typeof line.value}
            <span
              class={cn(
                !changed && (kind === 'number' ? 'text-series-1' : kind === 'string' ? 'text-fg' : 'text-series-3')
              )}>{text(line.value)}</span
            >
          {:else if line.folded}
            <span class="ml-1 rounded-sm bg-element-bg px-1.5 text-fg-muted">{line.size}</span>
          {/if}
        </span>
        {#if line.marks}
          {#each inlineAt.get(at) ?? [] as mark, index (index)}
            <span class="shrink-0 pr-3 font-sans">{@render mark.content(mark.data)}</span>
          {/each}
        {/if}
      </div>
      {#if line.marks}
        {#each blockAt.get(at) ?? [] as mark, index (index)}
          <div class="flex min-w-0">
            <span class={GUTTER}></span>
            <div class="min-w-0 flex-1 pr-4 font-sans" style:padding-left="{line.depth * 2}ch">
              {@render mark.content(mark.data)}
            </div>
          </div>
        {/each}
      {/if}
    {/if}
  {/each}
</div>
