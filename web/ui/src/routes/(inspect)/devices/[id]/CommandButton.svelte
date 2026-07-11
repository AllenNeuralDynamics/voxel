<script lang="ts">
  import { Button, Dialog, Select, TextInput } from '$lib/kit';
  import type { CommandInfo, DeviceHandle, ParamInfo } from '$lib/model';
  import { isErrorMsg } from '$lib/prop';
  import { SpinBox } from '$lib/prop/numeric';
  import { cn, sanitizeString } from '$lib/utils';

  interface Props {
    device: DeviceHandle;
    commandName: string;
    size?: 'xs' | 'sm' | 'md';
  }

  let { device, commandName, size = 'sm' }: Props = $props();

  const commandInfo = $derived(device.interface?.commands?.[commandName] as CommandInfo | undefined);

  const params = $derived.by(() => {
    if (!commandInfo) return [] as Array<[string, ParamInfo]>;
    return Object.entries(commandInfo.params).filter(([, p]) => p.kind === 'regular');
  });

  const hasParams = $derived(params.length > 0);

  let paramValues = $state<Record<string, unknown>>({});

  let open = $state(false);
  let executing = $state(false);
  let lastResult = $state<unknown>(null);

  const NUMERIC_TYPES = new Set(['int', 'float', 'number']);

  /** True if dtype is numeric, allowing `none` in unions (e.g. "float | none" but not "float | str"). */
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
      lastResult = hasParams ? await device.runCommand(commandName, [], kwargs) : await device.runCommand(commandName);
      if (!isErrorMsg(lastResult)) {
        open = false;
        lastResult = null;
      }
    } catch (e) {
      lastResult = { ok: false, msg: e instanceof Error ? e.message : String(e) };
    } finally {
      executing = false;
    }
  }

  const isError = $derived(lastResult != null && isErrorMsg(lastResult));
  const label = $derived(commandInfo?.label || sanitizeString(commandName));

  function formatResult(result: unknown): string {
    if (result == null) return 'null';
    if (isErrorMsg(result)) return result.msg;
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
                  options={param.options.map((o) => ({ value: String(o), label: String(o) }))}
                  onchange={(v) => (paramValues[name] = v)}
                  size="xs"
                />
              {:else if isNumericDtype(param.dtype)}
                <SpinBox
                  model={{
                    value: typeof paramValues[name] === 'number' ? paramValues[name] : (getDefaultValue(param) as number),
                    onChange: (v) => (paramValues[name] = v),
                    step: param.dtype.includes('int') ? 1 : 0.1
                  }}
                  steppers={false}
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

      {#if lastResult}
        <div
          class={cn('rounded border p-2', isError ? 'border-danger/30 bg-danger/5' : 'border-border bg-element-bg/30')}
        >
          <pre
            class={cn(
              'max-h-40 overflow-auto font-mono text-sm break-all whitespace-pre-wrap',
              isError ? 'text-danger' : 'text-fg'
            )}>{formatResult(lastResult)}</pre>
        </div>
      {/if}

      <Dialog.Footer>
        <Button variant="outline" onclick={() => (open = false)}>Close</Button>
        <Button onclick={execute} disabled={executing}>
          {executing ? 'Running…' : 'Execute'}
        </Button>
      </Dialog.Footer>
    </Dialog.Content>
  </Dialog.Root>
{/if}
