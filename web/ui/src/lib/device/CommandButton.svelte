<script lang="ts">
  import type { DevicesManager, CommandInfo, CommandResult, ParamInfo } from '$lib/app';
  import { isErrorMsg } from '$lib/app';
  import { cn, sanitizeString } from '$lib/utils';
  import { Button, Dialog, Select, SpinBox, TextInput } from '$lib/kit';

  interface Props {
    deviceId: string;
    commandName: string;
    devicesManager: DevicesManager;
    size?: 'xs' | 'sm' | 'md';
  }

  let { deviceId, commandName, devicesManager, size = 'sm' }: Props = $props();

  let device = $derived(devicesManager.getDevice(deviceId));
  let commandInfo = $derived(device?.interface?.commands[commandName] as CommandInfo | undefined);

  // Collect regular params
  let params = $derived.by(() => {
    if (!commandInfo) return [] as Array<[string, ParamInfo]>;
    return Object.entries(commandInfo.params).filter(([, p]) => p.kind === 'regular');
  });

  let hasParams = $derived(params.length > 0);

  // Reactive param values
  let paramValues = $state<Record<string, unknown>>({});

  // Dialog + execution state
  let open = $state(false);
  let executing = $state(false);
  let lastResult = $state<CommandResult | null>(null);

  const NUMERIC_TYPES = new Set(['int', 'float', 'number']);

  /** Check if dtype is numeric, allowing none in unions (e.g. "float | none" but not "float | str"). */
  function isNumericDtype(dtype: string): boolean {
    const types = dtype.split(' | ');
    return types.some((t) => NUMERIC_TYPES.has(t)) && types.every((t) => NUMERIC_TYPES.has(t) || t === 'none');
  }

  function getDefaultValue(param: ParamInfo): unknown {
    if (param.default != null) return param.default;
    if (param.dtype === 'str') return '';
    if (isNumericDtype(param.dtype)) return 0;
    if (param.dtype === 'bool') return false;
    return '';
  }

  async function execute() {
    if (!commandInfo || executing) return;
    executing = true;

    const kwargs: Record<string, unknown> = {};
    for (const [name, param] of params) {
      kwargs[name] = paramValues[name] ?? getDefaultValue(param);
    }

    try {
      lastResult = hasParams
        ? await devicesManager.executeCommand(deviceId, commandName, [], kwargs)
        : await devicesManager.executeCommand(deviceId, commandName);
      // Auto-close on success
      if (!isErrorMsg(lastResult.result)) {
        open = false;
        lastResult = null;
      }
    } catch (e) {
      lastResult = {
        device: deviceId,
        command: commandName,
        result: { msg: e instanceof Error ? e.message : String(e) }
      };
    } finally {
      executing = false;
    }
  }

  let isError = $derived(lastResult != null && isErrorMsg(lastResult.result));

  let label = $derived(commandInfo?.label || sanitizeString(commandName));

  function formatResult(result: unknown): string {
    if (result == null) return 'null';
    if (typeof result === 'string') return result;
    return JSON.stringify(result, null, 2);
  }
</script>

{#if commandInfo}
  <Dialog.Root bind:open>
    <Dialog.Trigger>
      {#snippet child({ props })}
        <Button variant="outline" {size} class="w-full" {...props}>{label}</Button>
      {/snippet}
    </Dialog.Trigger>

    <Dialog.Content size="xl">
      <Dialog.Header>
        <Dialog.Title>{label}</Dialog.Title>
        {#if commandInfo.desc}
          <Dialog.Description>{commandInfo.desc}</Dialog.Description>
        {/if}
      </Dialog.Header>

      <!-- Params -->
      {#if hasParams}
        <div class="grid gap-2">
          {#each params as [name, param] (name)}
            <div class="grid gap-1">
              <span class="text-xs font-medium text-fg-muted">
                {sanitizeString(name)}
              </span>
              {#if param.options && param.options.length > 0}
                <Select
                  value={typeof paramValues[name] === 'string' ? paramValues[name] : String(getDefaultValue(param))}
                  options={param.options.map((o: string) => ({ value: o, label: o }))}
                  onchange={(v) => (paramValues[name] = v)}
                  size="xs"
                />
              {:else if isNumericDtype(param.dtype)}
                <SpinBox
                  value={typeof paramValues[name] === 'number' ? paramValues[name] : (getDefaultValue(param) as number)}
                  onChange={(v) => (paramValues[name] = v)}
                  step={param.dtype.includes('int') ? 1 : 0.1}
                  appearance="bordered"
                  size="xs"
                />
              {:else}
                <TextInput
                  value={typeof paramValues[name] === 'string' ? paramValues[name] : String(getDefaultValue(param))}
                  onChange={(v) => (paramValues[name] = v)}
                  size="xs"
                />
              {/if}
            </div>
          {/each}
        </div>
      {/if}

      <!-- Result -->
      {#if lastResult}
        <div
          class={cn('rounded border p-2', isError ? 'border-danger/30 bg-danger/5' : 'border-border bg-element-bg/30')}
        >
          <pre
            class={cn(
              'max-h-40 overflow-auto font-mono text-sm break-all whitespace-pre-wrap',
              isError ? 'text-danger' : 'text-fg'
            )}>{formatResult(lastResult.result)}</pre>
        </div>
      {/if}

      <Dialog.Footer>
        <Button variant="outline" onclick={() => (open = false)}>Close</Button>
        <Button onclick={execute} disabled={executing}>
          {executing ? 'Running\u2026' : 'Execute'}
        </Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>
{/if}
