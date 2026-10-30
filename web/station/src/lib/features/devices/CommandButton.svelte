<script lang="ts">
  import { reportFailure } from '$lib/core/failures';
  import type { CommandInfo, DeviceHandle, ParamInfo } from '$lib/core/model';
  import { displayName, errorMessage } from '$lib/core/utils';
  import { Button, Dialog, NumberBox, Select, TextBox } from '$lib/kit';

  interface Props {
    device: DeviceHandle;
    commandName: string;
    disabled?: boolean;
  }

  const { device, commandName, disabled = false }: Props = $props();
  const NUMERIC_TYPES = ['int', 'float', 'number'];

  const commandInfo = $derived(device.interface?.commands?.[commandName] as CommandInfo | undefined);
  const params = $derived(
    Object.entries(commandInfo?.params ?? {}).filter(([, param]) => param.kind === 'regular') as [string, ParamInfo][]
  );
  const label = $derived(commandInfo?.label || displayName(commandName));
  let values = $state<Record<string, unknown>>({});
  let open = $state(false);
  let running = $state(false);
  /** Why the last run failed. The dialog stays open to show it. */
  let failure = $state<string | null>(null);

  function isNumeric(dtype: string): boolean {
    const types = dtype.split(' | ');
    return (
      types.some((type) => NUMERIC_TYPES.includes(type)) &&
      types.every((type) => NUMERIC_TYPES.includes(type) || type === 'none')
    );
  }

  function fallback(param: ParamInfo): unknown {
    if (param.default != null) return param.default;
    if (isNumeric(param.dtype)) return 0;
    if (param.dtype === 'bool') return false;
    return '';
  }

  async function run(): Promise<void> {
    if (!commandInfo || running) return;
    running = true;
    const kwargs = Object.fromEntries(params.map(([name, param]) => [name, values[name] ?? fallback(param)]));
    try {
      await (params.length ? device.runCommand(commandName, [], kwargs) : device.runCommand(commandName));
      open = false;
      failure = null;
    } catch (error) {
      failure = errorMessage(error);
      // The dialog shows the failure, so the Issues list keeps it without a toast.
      reportFailure(error, { toast: false });
    } finally {
      running = false;
    }
  }
</script>

{#if commandInfo}
  <Dialog.Root bind:open>
    <Dialog.Trigger {disabled}>
      {#snippet child({ props })}
        <Button variant="outline" class="w-full" title={commandInfo.desc || undefined} {...props}>{label}</Button>
      {/snippet}
    </Dialog.Trigger>
    <Dialog.Content size="md">
      <Dialog.Header>
        <Dialog.Title>{label}</Dialog.Title>
        {#if commandInfo.desc}<Dialog.Description>{commandInfo.desc}</Dialog.Description>{/if}
      </Dialog.Header>
      {#if params.length}
        <div class="grid grid-cols-[max-content_minmax(0,1fr)] items-center gap-x-3 gap-y-2">
          {#each params as [name, param] (name)}
            <span class="text-sm text-fg-muted">{displayName(name)}</span>
            {#if param.options?.length}
              <Select
                value={param.options.find((option) => option === (values[name] ?? fallback(param)))}
                options={param.options}
                onChange={(option) => (values[name] = option)}
                aria-label={displayName(name)}
              />
            {:else if isNumeric(param.dtype)}
              <NumberBox
                value={typeof values[name] === 'number' ? values[name] : (fallback(param) as number)}
                onChange={(value) => (values[name] = value)}
                step={param.dtype.includes('int') ? 1 : 0.1}
                aria-label={displayName(name)}
              />
            {:else}
              <TextBox
                live
                value={typeof values[name] === 'string' ? values[name] : String(fallback(param))}
                onChange={(value) => (values[name] = value)}
                aria-label={displayName(name)}
              />
            {/if}
          {/each}
        </div>
      {/if}
      {#if failure}
        <pre
          class="max-h-40 overflow-auto note-danger p-2 font-mono text-sm break-all whitespace-pre-wrap text-danger-fg">{failure}</pre>
      {/if}
      <Dialog.Footer>
        <Button size="lg" variant="ghost" onclick={() => (open = false)}>Close</Button>
        <Button size="lg" disabled={running} onclick={run}>{running ? 'Running…' : 'Run'}</Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>
{/if}
