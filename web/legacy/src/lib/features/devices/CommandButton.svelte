<script lang="ts">
  import type { DeviceHandle, OperationInfo } from '$lib/core/model';
  import type { ArgSchema } from '$lib/core/model/types';
  import { Button, Dialog, NumberBox, Select, TextBox } from '@voxel/kit';
  import { reportFailure } from '@voxel/kit/failures';
  import { errorMessage } from '@voxel/kit/failures';
  import { displayName } from '@voxel/kit/format';

  interface Props {
    device: DeviceHandle;
    commandName: string;
    disabled?: boolean;
  }

  const { device, commandName, disabled = false }: Props = $props();

  /** A parameter as the form uses it, read from the command's JSON Schema. */
  interface Param {
    name: string;
    required: boolean;
    type: string;
    default?: unknown;
    options?: (string | number)[];
  }

  const commandInfo = $derived(device.interface?.operations?.[commandName] as OperationInfo | undefined);
  const params = $derived(commandInfo ? readParams(commandInfo.params) : []);
  const label = $derived(commandInfo?.label || displayName(commandName));
  let values = $state<Record<string, unknown>>({});
  let open = $state(false);
  let running = $state(false);
  /** Why the last run failed. The dialog stays open to show it. */
  let failure = $state<string | null>(null);

  function resolveRef(schema: ArgSchema, root: ArgSchema): ArgSchema {
    const name = schema.$ref?.split('/').pop();
    return name && root.$defs?.[name] ? { ...root.$defs[name], ...schema, $ref: undefined } : schema;
  }

  /** The schema without its `null` branch, so `int | None` reads as `int`. */
  function nonNull(schema: ArgSchema, root: ArgSchema): ArgSchema {
    const resolved = resolveRef(schema, root);
    const branch = resolved.anyOf?.map((option) => resolveRef(option, root)).find((option) => option.type !== 'null');
    return branch ? { ...branch, default: resolved.default } : resolved;
  }

  function readParams(schema: ArgSchema): Param[] {
    const required = new Set(schema.required ?? []);
    return Object.entries(schema.properties ?? {}).map(([name, raw]) => {
      const field = nonNull(raw, schema);
      const type = Array.isArray(field.type)
        ? (field.type.find((t) => t !== 'null') ?? 'string')
        : (field.type ?? 'string');
      const options = field.enum?.filter(
        (option): option is string | number => typeof option !== 'boolean' && option !== null
      );
      return {
        name,
        required: required.has(name),
        type,
        default: field.default,
        options: options?.length ? options : undefined
      };
    });
  }

  function isNumeric(param: Param): boolean {
    return param.type === 'integer' || param.type === 'number';
  }

  function fallback(param: Param): unknown {
    if (param.default != null) return param.default;
    if (param.options?.length) return param.options[0];
    if (isNumeric(param)) return 0;
    if (param.type === 'boolean') return false;
    return '';
  }

  async function run(): Promise<void> {
    if (!commandInfo || running) return;
    running = true;
    // Optional arguments the user left alone keep the device's own default.
    const kwargs = Object.fromEntries(
      params
        .filter((param) => param.required || values[param.name] !== undefined)
        .map((param) => [param.name, values[param.name] ?? fallback(param)])
    );
    try {
      await (Object.keys(kwargs).length ? device.runCommand(commandName, [], kwargs) : device.runCommand(commandName));
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
          {#each params as param (param.name)}
            {@const name = param.name}
            <span class="text-sm text-fg-muted">{displayName(name)}</span>
            {#if param.options?.length}
              <Select
                value={param.options.find((option) => option === (values[name] ?? fallback(param)))}
                options={param.options}
                onChange={(option) => (values[name] = option)}
                aria-label={displayName(name)}
              />
            {:else if isNumeric(param)}
              <NumberBox
                value={typeof values[name] === 'number' ? values[name] : (fallback(param) as number)}
                onChange={(value) => (values[name] = value)}
                step={param.type === 'integer' ? 1 : 0.1}
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
