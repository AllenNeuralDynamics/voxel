<script lang="ts">
  import { watch } from 'runed';
  import { toast } from 'svelte-sonner';

  import { resolveDeviceColor, waveformPortColor } from '$lib/colors.svelte';
  import { Select } from '$lib/kit';
  import type { SelectOption } from '$lib/kit/Select.svelte';
  import type { DerivedWaveform, Signals, Waveform } from '$lib/model';
  import { getVoxelStation, ROLE_ORDER } from '$lib/model';
  import { SpinBox } from '$lib/prop/numeric';
  import { displayName, toastError } from '$lib/utils';

  import WaveformPlot, { type PlotContext } from './WaveformPlot.svelte';
  import {
    cloneWaveform,
    createWaveform,
    generateTraces,
    type GroupMode,
    groupWaveforms,
    isDerivedWaveform,
    resolveWaveforms
  } from './waveforms';

  const app = getVoxelStation();
  const instrument = $derived(app.instrument);
  const canEdit = $derived(instrument?.mode !== 'capture');
  const profile = $derived(instrument ? instrument.imaging.profiles[instrument.activeProfileId] : undefined);

  const waveformTypeOptions: SelectOption[] = [
    { value: 'pulse', label: 'Pulse' },
    { value: 'square', label: 'Square' },
    { value: 'sine', label: 'Sine' },
    { value: 'triangle', label: 'Triangle' },
    { value: 'multi_point', label: 'Multi-point' },
    { value: 'csv', label: 'CSV' },
    { value: 'derived', label: 'Derived' }
  ];

  const derivedOperationOptions: SelectOption[] = [
    { value: 'mirror', label: 'Mirror' },
    { value: 'scale', label: 'Scale' },
    { value: 'offset', label: 'Offset' },
    { value: 'shift', label: 'Shift' }
  ];

  const groupModeOptions: SelectOption<GroupMode>[] = [
    { value: 'related', label: 'Related' },
    { value: 'device-type', label: 'Device type' },
    { value: 'channel', label: 'Channel' }
  ];

  type VoltageMode = 'minmax' | 'ampoffset';
  type WindowMode = 'percent' | 'seconds';
  type RepeatMode = 'cycles' | 'frequency';
  interface Timing {
    sample_rate: number;
    duration: number;
    rest_time: number;
  }

  const defaultTiming: Timing = { sample_rate: 100000, duration: 0.01, rest_time: 0 };

  let selectedGeneratorUid = $state<string | null>(null);
  let groupMode = $state<GroupMode>('related');
  let selectedWaveformId = $state<string | null>(null);
  let editingWaveform = $state<Waveform | null>(null);
  let voltageMode = $state<VoltageMode>('minmax');
  let windowMode = $state<WindowMode>('seconds');
  let repeatMode = $state<RepeatMode>('cycles');

  const generatorUids = $derived<string[]>(profile ? Object.keys(profile.sync) : []);
  const generatorOptions = $derived<SelectOption[]>(
    generatorUids.map((uid) => ({ value: uid, label: displayName(uid) }))
  );

  watch(
    () => generatorUids,
    (uids) => {
      if (uids.length === 0) selectedGeneratorUid = null;
      else if (!selectedGeneratorUid || !uids.includes(selectedGeneratorUid)) selectedGeneratorUid = uids[0];
    }
  );

  const loadedSignals = $derived.by<Signals | null>(() => {
    if (!selectedGeneratorUid) return null;
    return instrument?.signalGenerators.get(selectedGeneratorUid)?.loaded ?? null;
  });

  const configSignals = $derived.by<Signals | null>(() => {
    if (!profile || !selectedGeneratorUid) return null;
    return profile.sync[selectedGeneratorUid] ?? null;
  });

  const baseWaveforms = $derived<Record<string, Waveform>>(loadedSignals?.waveforms ?? {});
  const waveformIds = $derived.by<string[]>(() => {
    const available = Object.keys(baseWaveforms);
    const ordered: string[] = [];
    const devices = [...(instrument?.devices.values() ?? [])].sort(
      (left, right) => ROLE_ORDER[left.role] - ROLE_ORDER[right.role] || left.roleIndex - right.roleIndex
    );
    for (const device of devices) {
      if (available.includes(device.id)) ordered.push(device.id);
    }
    for (const id of available) {
      if (!ordered.includes(id)) ordered.push(id);
    }
    return ordered;
  });

  const voltageRange = $derived.by<{ min: number; max: number } | null>(() => {
    if (!selectedGeneratorUid) return null;
    return instrument?.signalGenerators.get(selectedGeneratorUid)?.voltageRange ?? null;
  });

  const waveformColors = $derived.by<Record<string, string>>(() => {
    const result: Record<string, string> = {};
    let portIndex = 0;
    for (const id of waveformIds) {
      const device = instrument?.devices.get(id);
      const emission = instrument?.activeChannels.find(
        (channel) => channel.camera.id === id || channel.laser.id === id
      )?.emission;
      result[id] =
        (device && resolveDeviceColor(device.role, device.roleIndex, emission)) || waveformPortColor(portIndex++);
    }
    return result;
  });

  const channelGroups = $derived(
    (instrument?.activeChannels ?? []).map((channel) => ({
      id: channel.id,
      label: channel.label,
      deviceIds: [
        channel.camera.id,
        channel.laser.id,
        ...channel.filters.map((filter) => filter.wheel.id),
        ...channel.auxilliary.map((device) => device.id)
      ]
    }))
  );

  const displayWaveforms = $derived.by<Record<string, Waveform>>(() => {
    if (!selectedWaveformId || !editingWaveform) return baseWaveforms;
    return { ...baseWaveforms, [selectedWaveformId]: editingWaveform };
  });

  const groups = $derived(
    groupWaveforms({
      mode: groupMode,
      waveformIds,
      waveforms: displayWaveforms,
      roles: new Map([...(instrument?.devices.entries() ?? [])].map(([id, device]) => [id, device.role])),
      channels: channelGroups
    })
  );

  const plotHeight = $derived.by(() => {
    const count = Math.max(groups.length, 1);
    const headerHeightRem = 2.5;
    const totalGapRem = Math.max(count - 1, 0) * 0.75;
    const chromePerGroupRem = headerHeightRem + totalGapRem / count;
    return `clamp(10rem, calc(${100 / count}cqh - ${chromePerGroupRem}rem), 18rem)`;
  });

  function selectGenerator(uid: string) {
    if (uid === selectedGeneratorUid) return;
    flushPendingWaveformPatch();
    selectedWaveformId = null;
    editingWaveform = null;
    selectedGeneratorUid = uid;
  }

  function selectWaveform(id: string) {
    if (id === selectedWaveformId) {
      closeEditor();
      return;
    }
    const waveform = baseWaveforms[id];
    if (!waveform) return;
    flushPendingWaveformPatch();
    selectedWaveformId = id;
    editingWaveform = cloneWaveform(waveform);
  }

  function closeEditor() {
    flushPendingWaveformPatch();
    selectedWaveformId = null;
    editingWaveform = null;
  }

  watch(
    () => waveformIds,
    (ids) => {
      if (!selectedWaveformId || ids.includes(selectedWaveformId)) return;
      discardPendingWaveformPatch();
      selectedWaveformId = null;
      editingWaveform = null;
    }
  );

  watch(
    () => `${instrument?.activeProfileId ?? ''}:${selectedGeneratorUid ?? ''}`,
    () => {
      discardPendingWaveformPatch();
      selectedWaveformId = null;
      editingWaveform = null;
    },
    { lazy: true }
  );

  let localTiming = $state<Timing>({ ...defaultTiming });
  let timingTimer: ReturnType<typeof setTimeout> | null = null;
  let timingCommitInFlight = false;
  let timingDirty = false;
  let timingRevision = 0;

  function syncTiming(signals: Signals | null) {
    localTiming = signals
      ? {
          sample_rate: signals.sample_rate,
          duration: signals.duration,
          rest_time: signals.rest_time
        }
      : { ...defaultTiming };
  }

  watch(
    () => configSignals,
    (signals) => {
      if (!timingDirty) syncTiming(signals);
    }
  );

  watch(
    () => `${instrument?.activeProfileId ?? ''}:${selectedGeneratorUid ?? ''}`,
    () => {
      if (timingTimer) clearTimeout(timingTimer);
      timingTimer = null;
      timingDirty = false;
      timingRevision += 1;
      syncTiming(configSignals);
    },
    { lazy: true }
  );

  function updateTiming(field: keyof Timing, value: number) {
    if (!isFinite(value)) return;
    localTiming = { ...localTiming, [field]: value };
    timingDirty = true;
    timingRevision += 1;
    if (timingTimer) clearTimeout(timingTimer);
    timingTimer = setTimeout(() => {
      timingTimer = null;
      void commitTiming();
    }, 150);
  }

  async function commitTiming() {
    if (timingCommitInFlight) {
      if (timingTimer) clearTimeout(timingTimer);
      timingTimer = setTimeout(() => void commitTiming(), 150);
      return;
    }
    if (!canEdit || !timingDirty || !selectedGeneratorUid || !configSignals) return;

    const generatorUid = selectedGeneratorUid;
    const revision = timingRevision;
    const signals: Signals = { ...localTiming, waveforms: configSignals.waveforms };
    timingCommitInFlight = true;
    try {
      await instrument?.updateSignals(generatorUid, signals);
      if (selectedGeneratorUid === generatorUid && timingRevision === revision) timingDirty = false;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update clock');
      if (selectedGeneratorUid === generatorUid && timingRevision === revision) {
        timingDirty = false;
        syncTiming(configSignals);
      }
    } finally {
      timingCommitInFlight = false;
      if (timingDirty && timingRevision !== revision) {
        timingTimer = setTimeout(() => void commitTiming(), 150);
      }
    }
  }

  const duration = $derived(localTiming.duration);
  const restTime = $derived(localTiming.rest_time);
  const sampleRate = $derived(localTiming.sample_rate);
  const resolvedWaveforms = $derived(resolveWaveforms(displayWaveforms));
  const plotData = $derived(generateTraces(displayWaveforms, duration, restTime));

  function groupYRange(ids: string[]): { min: number; max: number } {
    let min = Infinity;
    let max = -Infinity;
    for (const id of ids) {
      const waveform = resolvedWaveforms[id];
      if (!waveform) continue;
      const rest = waveform.rest_voltage ?? waveform.voltage.min;
      min = Math.min(min, waveform.voltage.min, rest);
      max = Math.max(max, waveform.voltage.max, rest);
    }
    if (!isFinite(min) || !isFinite(max)) return { min: 0, max: 1 };
    if (min === max) return { min: min - 0.1, max: max + 0.1 };
    const padding = (max - min) * 0.05;
    return { min: min - padding, max: max + padding };
  }

  const plotContext = $derived<PlotContext>({
    duration,
    restTime,
    voltageRange,
    syncKey: `sync:${selectedGeneratorUid ?? 'none'}`
  });

  const editFingerprint = $derived.by<string | null>(() => {
    if (!selectedWaveformId || !editingWaveform) return null;
    return JSON.stringify({
      id: selectedWaveformId,
      waveform: $state.snapshot(editingWaveform)
    });
  });

  interface PendingWaveformPatch {
    generatorUid: string;
    waveformId: string;
    waveform: Waveform;
    base: Signals;
  }

  let waveformPatchTimer: ReturnType<typeof setTimeout> | null = null;
  let pendingWaveformPatch: PendingWaveformPatch | null = null;

  function sendWaveformPatch(patch: PendingWaveformPatch) {
    const signals: Signals = {
      sample_rate: patch.base.sample_rate,
      duration: patch.base.duration,
      rest_time: patch.base.rest_time,
      waveforms: { ...patch.base.waveforms, [patch.waveformId]: patch.waveform }
    };
    toastError(instrument?.updateSignals(patch.generatorUid, signals));
  }

  function discardPendingWaveformPatch() {
    if (waveformPatchTimer) clearTimeout(waveformPatchTimer);
    waveformPatchTimer = null;
    pendingWaveformPatch = null;
  }

  function flushPendingWaveformPatch() {
    if (waveformPatchTimer) clearTimeout(waveformPatchTimer);
    waveformPatchTimer = null;
    const patch = pendingWaveformPatch;
    pendingWaveformPatch = null;
    if (patch) sendWaveformPatch(patch);
  }

  watch(
    () => editFingerprint,
    (fingerprint) => {
      if (
        !fingerprint ||
        !canEdit ||
        !selectedGeneratorUid ||
        !selectedWaveformId ||
        !editingWaveform ||
        !configSignals
      ) {
        discardPendingWaveformPatch();
        return;
      }
      if (waveformPatchTimer) clearTimeout(waveformPatchTimer);
      pendingWaveformPatch = {
        generatorUid: selectedGeneratorUid,
        waveformId: selectedWaveformId,
        waveform: cloneWaveform(editingWaveform),
        base: configSignals
      };
      waveformPatchTimer = setTimeout(() => {
        waveformPatchTimer = null;
        const patch = pendingWaveformPatch;
        pendingWaveformPatch = null;
        if (patch) sendWaveformPatch(patch);
      }, 150);
    },
    { lazy: true }
  );

  $effect(() => {
    return () => {
      if (timingTimer) clearTimeout(timingTimer);
      if (waveformPatchTimer) clearTimeout(waveformPatchTimer);
    };
  });

  function updateEditingField(field: string, value: unknown) {
    if (!editingWaveform) return;
    if (typeof value === 'number' && !isFinite(value)) return;
    (editingWaveform as unknown as Record<string, unknown>)[field] = value;
  }

  function updateWindow(key: 'min' | 'max', value: number) {
    if (!editingWaveform || isDerivedWaveform(editingWaveform) || !isFinite(value)) return;
    editingWaveform.window[key] = value;
  }

  function updateVoltage(key: 'min' | 'max', value: number) {
    if (!editingWaveform || isDerivedWaveform(editingWaveform) || !isFinite(value)) return;
    const clamped = voltageRange ? Math.max(voltageRange.min, Math.min(voltageRange.max, value)) : value;
    editingWaveform.voltage[key] = clamped;
    const rest = editingWaveform.rest_voltage ?? editingWaveform.voltage.min;
    editingWaveform.rest_voltage = Math.max(editingWaveform.voltage.min, Math.min(editingWaveform.voltage.max, rest));
  }

  function updateAmplitude(amplitude: number) {
    if (!editingWaveform || isDerivedWaveform(editingWaveform)) return;
    const offset = (editingWaveform.voltage.max + editingWaveform.voltage.min) / 2;
    const value = Math.max(0, amplitude);
    updateVoltage('min', offset - value);
    updateVoltage('max', offset + value);
  }

  function updateOffset(offset: number) {
    if (!editingWaveform || isDerivedWaveform(editingWaveform)) return;
    const amplitude = (editingWaveform.voltage.max - editingWaveform.voltage.min) / 2;
    updateVoltage('min', offset - amplitude);
    updateVoltage('max', offset + amplitude);
  }

  function changeWaveformType(type: string) {
    if (!editingWaveform || !selectedWaveformId) return;
    const waveform = createWaveform(editingWaveform, type, baseWaveforms, selectedWaveformId);
    if (waveform) editingWaveform = waveform;
  }

  function changeDerivedOperation(operation: string) {
    if (!editingWaveform || !isDerivedWaveform(editingWaveform)) return;
    const source = editingWaveform.source;
    switch (operation) {
      case 'mirror':
        editingWaveform = { type: 'derived', operation, source };
        break;
      case 'scale':
        editingWaveform = { type: 'derived', operation, source, factor: 1 };
        break;
      case 'offset':
        editingWaveform = { type: 'derived', operation, source, delta: 0 };
        break;
      case 'shift':
        editingWaveform = { type: 'derived', operation, source, fraction: 0 };
        break;
    }
  }

  function changeDerivedSource(source: string) {
    if (!editingWaveform || !isDerivedWaveform(editingWaveform)) return;
    (editingWaveform as DerivedWaveform).source = source;
  }

  const derivedSourceOptions = $derived<SelectOption[]>(
    waveformIds.filter((id) => id !== selectedWaveformId).map((id) => ({ value: id, label: displayName(id) }))
  );

  const activeWindowSeconds = $derived(
    !editingWaveform || isDerivedWaveform(editingWaveform)
      ? 0
      : duration * (editingWaveform.window.max - editingWaveform.window.min)
  );
  const cycleCount = $derived(
    editingWaveform &&
      !isDerivedWaveform(editingWaveform) &&
      'cycles' in editingWaveform &&
      editingWaveform.cycles != null
      ? editingWaveform.cycles
      : 1
  );
  const cycleFrequency = $derived(activeWindowSeconds > 0 ? cycleCount / activeWindowSeconds : 0);

  function updateCycleCount(value: number) {
    updateEditingField('cycles', value);
    updateEditingField('frequency', null);
  }

  function updateCycleFrequency(value: number) {
    if (activeWindowSeconds <= 0) return;
    updateEditingField('cycles', value * activeWindowSeconds);
    updateEditingField('frequency', null);
  }
</script>

{#if profile}
  <div class="flex h-full min-h-0 flex-col">
    <header class="shrink-0 border-b py-2">
      <div class="flex items-center gap-3 px-4 py-1.5">
        <Select
          prefix="Generator"
          size="xs"
          class="w-54"
          value={selectedGeneratorUid ?? ''}
          options={generatorOptions}
          disabled={generatorOptions.length === 0}
          onchange={selectGenerator}
        />
        <Select
          prefix="Group by"
          size="xs"
          class="ml-auto w-54"
          value={groupMode}
          options={groupModeOptions}
          onchange={(value) => (groupMode = value as GroupMode)}
        />
      </div>
      <div class="flex items-center gap-2 px-4 py-1.5" aria-label="Clock timing">
        <SpinBox
          model={{
            value: sampleRate / 1000,
            onChange: (value) => updateTiming('sample_rate', value * 1000),
            min: 0.001,
            step: 0.001,
            bigStep: 1
          }}
          prefix="Sample rate"
          suffix=" kHz"
          size="xs"
          numCharacters={7}
          align="right"
          steppers={false}
          disabled={!canEdit}
          class="min-w-52 flex-1"
        />
        <SpinBox
          model={{
            value: duration * 1000,
            onChange: (value) => updateTiming('duration', value / 1000),
            min: 0.1,
            step: 0.1,
            bigStep: 1
          }}
          prefix="Active"
          suffix=" ms"
          size="xs"
          numCharacters={7}
          align="right"
          steppers={false}
          disabled={!canEdit}
          class="min-w-36 flex-1"
        />
        <SpinBox
          model={{
            value: restTime * 1000,
            onChange: (value) => updateTiming('rest_time', value / 1000),
            min: 0,
            step: 0.1,
            bigStep: 1
          }}
          prefix="Rest"
          suffix=" ms"
          size="xs"
          numCharacters={5}
          align="right"
          steppers={false}
          disabled={!canEdit}
          class="min-w-36 flex-1"
        />
      </div>
    </header>

    <main class="sync-viewport min-h-0 flex-1 overflow-y-auto p-4">
      <div class="mx-auto flex w-full max-w-7xl flex-col gap-3">
        {#each groups as group (group.id)}
          {@const colors = group.waveformIds.map((id) => waveformColors[id] ?? '#888')}
          {@const traces = group.waveformIds.map((id) => plotData.traces[id] ?? [])}
          {@const selectedInGroup = selectedWaveformId && group.waveformIds.includes(selectedWaveformId)}
          <section
            class="overflow-hidden rounded-xs border bg-canvas transition-colors
              {selectedInGroup ? 'border-focused/60' : 'border-border'}"
            aria-label={group.label || group.waveformIds.map(displayName).join(', ')}
          >
            <div class="flex min-h-10 flex-wrap items-center gap-1 border-b px-3 py-1.5">
              {#if group.label}
                <span class="mr-2 text-xs font-semibold tracking-wide text-fg-muted uppercase">{group.label}</span>
              {/if}
              {#each group.waveformIds as waveformId (waveformId)}
                {@const color = waveformColors[waveformId] ?? '#888'}
                {#if waveformId === selectedWaveformId && editingWaveform}
                  <div class="flex shrink-0 items-stretch" role="group" aria-label={`${displayName(waveformId)} type`}>
                    <button
                      type="button"
                      onclick={() => selectWaveform(waveformId)}
                      class="flex cursor-pointer items-center gap-1.5 rounded-l-full border border-border bg-element-selected px-2 py-0.5 text-base text-fg transition-colors"
                      aria-pressed="true"
                    >
                      <span class="size-2 shrink-0 rounded-full" style="background-color: {color}" aria-hidden="true"
                      ></span>
                      {displayName(waveformId)}
                    </button>
                    <Select
                      prefix=" "
                      size="xs"
                      class="-ml-px w-28 rounded-l-none rounded-r-full"
                      value={editingWaveform.type}
                      options={waveformTypeOptions}
                      disabled={!canEdit}
                      onchange={changeWaveformType}
                    />
                  </div>
                {:else}
                  <button
                    type="button"
                    onclick={() => selectWaveform(waveformId)}
                    class="flex cursor-pointer items-center gap-1.5 rounded-full border border-transparent px-2 py-0.5 text-base text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
                    aria-pressed="false"
                  >
                    <span class="size-2 shrink-0 rounded-full" style="background-color: {color}" aria-hidden="true"
                    ></span>
                    {displayName(waveformId)}
                  </button>
                {/if}
              {/each}
            </div>

            <div class="shrink-0 p-2" style:height={plotHeight}>
              <WaveformPlot
                time={plotData.time}
                {traces}
                {colors}
                yRange={groupYRange(group.waveformIds)}
                context={plotContext}
              />
            </div>

            {#if selectedInGroup && selectedWaveformId && editingWaveform}
              {@const waveform = editingWaveform}
              <div class="border-t bg-element-bg/35">
                {#if isDerivedWaveform(waveform)}
                  <div class="inspector-body px-4 py-3">
                    <div class="property-row">
                      <h3 class="text-xs font-semibold tracking-wider text-fg-muted uppercase">Derived</h3>
                      <div class="property-controls">
                        <Select
                          prefix="Operation"
                          size="xs"
                          class="w-full"
                          value={waveform.operation}
                          options={derivedOperationOptions}
                          disabled={!canEdit}
                          onchange={changeDerivedOperation}
                        />
                        <Select
                          prefix="Source"
                          size="xs"
                          class="w-full"
                          value={waveform.source}
                          options={derivedSourceOptions}
                          disabled={!canEdit || derivedSourceOptions.length === 0}
                          onchange={changeDerivedSource}
                        />
                        {#if waveform.operation === 'scale'}
                          <SpinBox
                            model={{
                              value: waveform.factor,
                              onChange: (value) => updateEditingField('factor', value),
                              step: 0.05
                            }}
                            prefix="Factor"
                            size="xs"
                            numCharacters={8}
                            align="right"
                            disabled={!canEdit}
                            class="w-full"
                          />
                        {:else if waveform.operation === 'offset'}
                          <SpinBox
                            model={{
                              value: waveform.delta,
                              onChange: (value) => updateEditingField('delta', value),
                              step: 0.01
                            }}
                            prefix="Delta"
                            suffix=" V"
                            size="xs"
                            numCharacters={8}
                            align="right"
                            disabled={!canEdit}
                            class="w-full"
                          />
                        {:else if waveform.operation === 'shift'}
                          <SpinBox
                            model={{
                              value: waveform.fraction,
                              onChange: (value) => updateEditingField('fraction', value),
                              min: 0,
                              max: 1,
                              step: 0.01
                            }}
                            prefix="Fraction"
                            size="xs"
                            numCharacters={8}
                            align="right"
                            disabled={!canEdit}
                            class="w-full"
                          />
                        {/if}
                      </div>
                    </div>
                  </div>
                {:else}
                  <div class="inspector-body flex flex-col gap-x-2 gap-y-4 px-4 py-3">
                    <div class="property-row">
                      <h3 class="text-xs font-semibold tracking-wider text-fg-muted uppercase">Timing</h3>
                      <div class="property-controls">
                        <Select
                          prefix="Mode"
                          size="xs"
                          class="w-full"
                          value={windowMode}
                          options={[
                            { value: 'percent', label: 'Percent' },
                            { value: 'seconds', label: 'Seconds' }
                          ]}
                          disabled={!canEdit}
                          onchange={(value) => (windowMode = value as WindowMode)}
                        />
                        <SpinBox
                          model={{
                            value: windowMode === 'percent' ? waveform.window.min : waveform.window.min * duration,
                            onChange: (value) =>
                              updateWindow(
                                'min',
                                windowMode === 'percent' ? value : duration > 0 ? value / duration : 0
                              ),
                            min: 0,
                            max: windowMode === 'percent' ? waveform.window.max : waveform.window.max * duration,
                            step: windowMode === 'percent' ? 0.001 : 0.0001,
                            bigStep: windowMode === 'percent' ? 0.05 : 0.001
                          }}
                          prefix="Start"
                          suffix={windowMode === 'seconds' ? ' s' : undefined}
                          size="xs"
                          numCharacters={8}
                          align="right"
                          disabled={!canEdit || (windowMode === 'seconds' && duration <= 0)}
                          class="w-full"
                        />
                        <SpinBox
                          model={{
                            value: windowMode === 'percent' ? waveform.window.max : waveform.window.max * duration,
                            onChange: (value) =>
                              updateWindow(
                                'max',
                                windowMode === 'percent' ? value : duration > 0 ? value / duration : 0
                              ),
                            min: windowMode === 'percent' ? waveform.window.min : waveform.window.min * duration,
                            max: windowMode === 'percent' ? 1 : duration,
                            step: windowMode === 'percent' ? 0.001 : 0.0001,
                            bigStep: windowMode === 'percent' ? 0.05 : 0.001
                          }}
                          prefix="End"
                          suffix={windowMode === 'seconds' ? ' s' : undefined}
                          size="xs"
                          numCharacters={8}
                          align="right"
                          disabled={!canEdit || (windowMode === 'seconds' && duration <= 0)}
                          class="w-full"
                        />
                      </div>
                    </div>

                    <div class="property-row">
                      <h3 class="text-xs font-semibold tracking-wider text-fg-muted uppercase">Voltage</h3>
                      <div class="property-controls">
                        <Select
                          prefix="Mode"
                          size="xs"
                          class="w-full"
                          value={voltageMode}
                          options={[
                            { value: 'minmax', label: 'Min / Max' },
                            { value: 'ampoffset', label: 'Amp / Offset' }
                          ]}
                          disabled={!canEdit}
                          onchange={(value) => (voltageMode = value as VoltageMode)}
                        />
                        <SpinBox
                          model={{
                            value:
                              voltageMode === 'minmax'
                                ? waveform.voltage.min
                                : (waveform.voltage.max - waveform.voltage.min) / 2,
                            onChange:
                              voltageMode === 'minmax' ? (value) => updateVoltage('min', value) : updateAmplitude,
                            min: voltageMode === 'minmax' ? voltageRange?.min : 0,
                            max: voltageMode === 'minmax' ? waveform.voltage.max : undefined,
                            step: 0.001
                          }}
                          prefix={voltageMode === 'minmax' ? 'Min' : 'Amp'}
                          suffix=" V"
                          size="xs"
                          numCharacters={8}
                          align="right"
                          disabled={!canEdit}
                          class="w-full"
                        />
                        <SpinBox
                          model={{
                            value:
                              voltageMode === 'minmax'
                                ? waveform.voltage.max
                                : (waveform.voltage.max + waveform.voltage.min) / 2,
                            onChange: voltageMode === 'minmax' ? (value) => updateVoltage('max', value) : updateOffset,
                            min: voltageMode === 'minmax' ? waveform.voltage.min : voltageRange?.min,
                            max: voltageRange?.max,
                            step: 0.001
                          }}
                          prefix={voltageMode === 'minmax' ? 'Max' : 'Offset'}
                          suffix=" V"
                          size="xs"
                          numCharacters={8}
                          align="right"
                          disabled={!canEdit}
                          class="w-full"
                        />
                        <SpinBox
                          model={{
                            value: waveform.rest_voltage ?? waveform.voltage.min,
                            onChange: (value) => updateEditingField('rest_voltage', value),
                            min: waveform.voltage.min,
                            max: waveform.voltage.max,
                            step: 0.001,
                            home: () => waveform.voltage.min
                          }}
                          prefix="Rest"
                          suffix=" V"
                          size="xs"
                          numCharacters={8}
                          align="right"
                          disabled={!canEdit}
                          class="w-full"
                        />
                      </div>
                    </div>

                    {#if waveform.type === 'square' || waveform.type === 'sine' || waveform.type === 'triangle' || waveform.type === 'sawtooth'}
                      <div class="property-row">
                        <h3 class="text-xs font-semibold tracking-wider text-fg-muted uppercase">Shape</h3>
                        <div class="property-controls">
                          <Select
                            prefix="Mode"
                            size="xs"
                            class="w-full"
                            value={repeatMode}
                            options={[
                              { value: 'cycles', label: 'Cycles' },
                              { value: 'frequency', label: 'Frequency' }
                            ]}
                            disabled={!canEdit}
                            onchange={(value) => (repeatMode = value as RepeatMode)}
                          />
                          <label class="min-w-0">
                            <span class="sr-only">{repeatMode === 'cycles' ? 'Cycles' : 'Frequency'}</span>
                            <SpinBox
                              model={{
                                value: repeatMode === 'cycles' ? cycleCount : cycleFrequency,
                                onChange: repeatMode === 'cycles' ? updateCycleCount : updateCycleFrequency,
                                min: 0.001,
                                step: repeatMode === 'cycles' ? 0.25 : 0.01
                              }}
                              suffix={repeatMode === 'frequency' ? ' Hz' : undefined}
                              size="xs"
                              numCharacters={8}
                              align="right"
                              disabled={!canEdit || (repeatMode === 'frequency' && activeWindowSeconds <= 0)}
                              class="w-full"
                            />
                          </label>
                          {#if waveform.type === 'square'}
                            <SpinBox
                              model={{
                                value: waveform.duty_cycle,
                                onChange: (value) => updateEditingField('duty_cycle', value),
                                min: 0,
                                max: 1,
                                step: 0.001
                              }}
                              prefix="Duty"
                              size="xs"
                              numCharacters={8}
                              align="right"
                              disabled={!canEdit}
                              class="w-full"
                            />
                          {:else if waveform.type === 'triangle' || waveform.type === 'sawtooth'}
                            <SpinBox
                              model={{
                                value: waveform.symmetry ?? 1,
                                onChange: (value) => updateEditingField('symmetry', value),
                                min: 0,
                                max: 1,
                                step: 0.001
                              }}
                              prefix="Symmetry"
                              size="xs"
                              numCharacters={8}
                              align="right"
                              disabled={!canEdit}
                              class="w-full"
                            />
                          {/if}
                          <SpinBox
                            model={{
                              value: (waveform.phase ?? 0) * (180 / Math.PI),
                              onChange: (value) => updateEditingField('phase', value * (Math.PI / 180)),
                              step: 0.01
                            }}
                            prefix="Phase"
                            suffix=" deg"
                            size="xs"
                            numCharacters={8}
                            align="right"
                            disabled={!canEdit}
                            class="w-full"
                          />
                        </div>
                      </div>
                    {/if}
                  </div>
                {/if}
              </div>
            {/if}
          </section>
        {/each}

        {#if groups.length === 0}
          <div class="flex min-h-56 items-center justify-center text-lg text-fg-muted">No synchronized outputs</div>
        {/if}
      </div>
    </main>
  </div>
{:else}
  <div class="flex h-full items-center justify-center text-lg text-fg-muted">
    Select a profile to view synchronized outputs
  </div>
{/if}

<style>
  .sync-viewport {
    container-type: size;
  }

  .inspector-body {
    container-type: inline-size;
  }

  .property-row {
    display: grid;
    grid-template-columns: 5rem minmax(0, 1fr);
    align-items: start;
    gap: 0.5rem;
  }

  .property-row > h3 {
    padding-top: 0.5rem;
  }

  .property-controls {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.5rem;
  }

  @container (max-width: 50rem) {
    .property-row {
      grid-template-columns: minmax(0, 1fr);
    }

    .property-row > h3 {
      padding-top: 0;
    }
  }
</style>
