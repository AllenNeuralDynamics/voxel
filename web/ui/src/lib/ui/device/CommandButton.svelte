<script lang="ts">
	import type { DevicesManager, CommandInfo, CommandResult, ParamInfo } from '$lib/main';
	import { isErrorMsg } from '$lib/main';
	import { cn, sanitizeString } from '$lib/utils';
	import { Button, Dialog, SpinBox, TextInput } from '$lib/ui/kit';

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

	function getDefaultValue(param: ParamInfo): unknown {
		if (param.default != null) return param.default;
		if (param.dtype === 'str') return '';
		if (param.dtype === 'int' || param.dtype === 'float' || param.dtype === 'number') return 0;
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
							<span class="text-fg-muted text-xs font-medium">
								{sanitizeString(name)}
							</span>
							{#if param.dtype === 'int' || param.dtype === 'float' || param.dtype === 'number'}
								<SpinBox
									value={typeof paramValues[name] === 'number' ? paramValues[name] : (getDefaultValue(param) as number)}
									onChange={(v) => (paramValues[name] = v)}
									step={param.dtype === 'int' ? 1 : 0.1}
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
					class={cn('rounded border p-2', isError ? 'border-danger/30 bg-danger/5' : 'bg-element-bg/30 border-border')}
				>
					<pre
						class={cn('max-h-40 overflow-auto font-mono text-sm', isError ? 'text-danger' : 'text-fg')}>{formatResult(
							lastResult.result
						)}</pre>
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
