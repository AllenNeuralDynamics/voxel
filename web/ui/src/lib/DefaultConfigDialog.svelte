<script lang="ts" module>
  export type DefaultDialogMode = 'save' | 'restore';

  class DefaultDialogController {
    mode = $state<DefaultDialogMode | null>(null);

    open(mode: DefaultDialogMode): void {
      this.mode = mode;
    }

    close(): void {
      this.mode = null;
    }
  }

  export const defaultDialog = new DefaultDialogController();
</script>

<script lang="ts">
  import { Button, Dialog } from '$lib/kit';
  import { getVoxelApp } from '$lib/model';
  import { toastError } from '$lib/utils';

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);
  const restoring = $derived(defaultDialog.mode === 'restore');
  const title = $derived(restoring ? 'Restore default' : 'Save as default');
  const base = $derived(instrument?.default);
  const current = $derived(instrument?.state);

  function confirm(): void {
    if (!instrument || defaultDialog.mode === null) return;
    const action = restoring ? instrument.restoreDefault() : instrument.saveAsDefault();
    defaultDialog.close();
    toastError(action);
  }
  interface JsonDiff {
    path: string[];
    current: unknown;
    base: unknown;
  }

  function isRecord(x: unknown): x is Record<string, unknown> {
    return typeof x === 'object' && x !== null && !Array.isArray(x);
  }

  function jsonDivergence(cur: unknown, def: unknown, path: string[] = []): JsonDiff[] {
    if (isRecord(cur) && isRecord(def)) {
      const keys = [...new Set([...Object.keys(def), ...Object.keys(cur)])];
      return keys.flatMap((k) => jsonDivergence(cur[k], def[k], [...path, k]));
    }
    if (JSON.stringify(cur) === JSON.stringify(def)) return [];
    return [{ path, current: cur, base: def }];
  }

  const changes = $derived.by((): JsonDiff[] => {
    if (!base || !current) return [];
    const scoped = Object.fromEntries(
      Object.keys(base).map((k) => [k, (current as unknown as Record<string, unknown>)[k]])
    );
    return jsonDivergence(scoped, base).filter((d) => d.current !== undefined && d.base !== undefined);
  });

  function fmt(v: unknown): string {
    return typeof v === 'string' ? v : JSON.stringify(v);
  }
</script>

<Dialog.Root open={defaultDialog.mode !== null} onOpenChange={(o) => !o && defaultDialog.close()}>
  <Dialog.Content size="xxl" showCloseButton={false}>
    <Dialog.Header>
      <Dialog.Title>{title}</Dialog.Title>
    </Dialog.Header>
    <p class="text-lg text-fg-muted">
      {restoring ? 'Overwrite the current bench with the saved default.' : 'Save the current bench as the new default.'}
    </p>
    {#if instrument}
      <div class="max-h-[60dvh] overflow-auto rounded border border-border bg-card px-3 py-2">
        {#if changes.length === 0}
          <p class="text-base text-fg-muted">Matches default.</p>
        {:else}
          <div class="space-y-1">
            {#each changes as { path, current: cur, base: def } (path.join('.'))}
              <div class="flex items-baseline gap-2 font-mono text-base">
                <span class="text-fg-muted">{path.join('/')}</span>
                <span class="text-warning">{fmt(cur)}</span>
                <span class="text-fg-faint">({fmt(def)})</span>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {/if}
    <Dialog.Footer>
      <Button variant="ghost" onclick={() => defaultDialog.close()}>Cancel</Button>
      <Button variant={restoring ? 'danger' : 'default'} onclick={confirm}>{title}</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
