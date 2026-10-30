<script lang="ts">
  import { watch } from 'runed';

  import { getPageInstrument, getVoxelStation } from '$lib/context.svelte';
  import { reportFailure } from '$lib/core/failures';
  import type { DerivedWaveform, Signals, Waveform } from '$lib/core/model';
  import { ROLE_ORDER } from '$lib/core/model';
  import { displayName } from '$lib/core/utils';
  import WaveformPlot, { type PlotContext } from '$lib/features/imaging/WaveformPlot.svelte';
  import {
    cloneWaveform,
    createWaveform,
    generateTraces,
    type GroupMode,
    groupWaveforms,
    isDerivedWaveform,
    resolveWaveforms
  } from '$lib/features/imaging/waveforms';
  import { NumberBox, Select, SpinBox } from '$lib/kit';
  import { resolveDeviceColor, waveformPortColor } from '$lib/kit/themes/colors';
  import { profileHref } from '$lib/navigation';
  import PageFallback from '$lib/shell/PageFallback.svelte';
  import PageHeader from '$lib/shell/PageHeader.svelte';

  import type { PageProps } from './$types';

  let { params }: PageProps = $props();

  const app = getVoxelStation();
  const selected = getPageInstrument();
  const instrument = $derived(app.instrument);
  // Synchronized outputs only reload while nothing streams.
  const canEdit = $derived(instrument?.activity.kind === 'idle');
  const profile = $derived(instrument ? instrument.imaging.profiles[instrument.activeProfileId] : undefined);

  const WAVEFORM_TYPE_LABELS: Record<string, string> = {
    pulse: 'Pulse',
    square: 'Square',
    sine: 'Sine',
    triangle: 'Triangle',
    multi_point: 'Multi-point',
    csv: 'CSV',
    derived: 'Derived'
  };
  const WAVEFORM_TYPES = Object.keys(WAVEFORM_TYPE_LABELS);
  const DERIVED_OPERATIONS: DerivedWaveform['operation'][] = ['mirror', 'scale', 'offset', 'shift'];
  const GROUP_MODE_LABELS: Record<GroupMode, string> = {
    related: 'Related',
    'device-type': 'Device type',
    channel: 'Channel'
  };
  const GROUP_MODES = Object.keys(GROUP_MODE_LABELS) as GroupMode[];

  type VoltageMode = 'minmax' | 'ampoffset';
  type WindowMode = 'percent' | 'seconds';
  type RepeatMode = 'cycles' | 'frequency';
  interface Timing {
    sample_rate: number;
    duration: number;
    rest_time: number;
  }

  const defaultTiming: Timing = { sample_rate: 100000, duration: 0.01, rest_time: 0 };

  const selectedGeneratorUid = $derived(params.generatorId);
  const profileItem = $derived({
    label: profile?.label || displayName(params.profileId),
    href: profileHref(selected.params, params.profileId)
  });
  let groupMode = $state<GroupMode>('related');
  let selectedWaveformId = $state<string | null>(null);
  let editingWaveform = $state<Waveform | null>(null);
  let voltageMode = $state<VoltageMode>('minmax');
  let windowMode = $state<WindowMode>('seconds');
  let repeatMode = $state<RepeatMode>('cycles');

  const generatorConfigured = $derived(
    Boolean(profile && selectedGeneratorUid && Object.hasOwn(profile.sync, selectedGeneratorUid))
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
    () => `${instrument?.activeProfileId ?? ''}:${selectedGeneratorUid}`,
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
    () => `${instrument?.activeProfileId ?? ''}:${selectedGeneratorUid}`,
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
      reportFailure(error);
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
    reportFailure(instrument?.updateSignals(patch.generatorUid, signals));
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

  const derivedSources = $derived(waveformIds.filter((id) => id !== selectedWaveformId));

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

{#if profile && generatorConfigured}
  <PageHeader items={[profileItem, { label: displayName(selectedGeneratorUid) }]}>
    {#snippet trailing()}
      <Select
        prefix="Group by"
        class="w-54"
        value={groupMode}
        options={GROUP_MODES}
        formatLabel={(mode) => GROUP_MODE_LABELS[mode]}
        onChange={(mode) => (groupMode = mode)}
      />
    {/snippet}
  </PageHeader>

  <div class="sync-viewport page-body">
    <div class="mx-auto flex w-full max-w-7xl flex-col gap-3">
      {#each groups as group (group.id)}
        {@const colors = group.waveformIds.map((id) => waveformColors[id] ?? '#888')}
        {@const traces = group.waveformIds.map((id) => plotData.traces[id] ?? [])}
        {@const selectedInGroup = selectedWaveformId && group.waveformIds.includes(selectedWaveformId)}
        <div
          class="overflow-hidden rounded-xs border bg-canvas transition-colors
            {selectedInGroup ? 'border-line-selected' : 'border-line-muted'}"
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
                    class="flex cursor-pointer items-center gap-1.5 rounded-l-full border border-line-selected bg-element-selected px-2 py-0.5 text-base text-fg transition-colors"
                    aria-pressed="true"
                  >
                    <span class="size-2 shrink-0 rounded-full" style="background-color: {color}" aria-hidden="true"
                    ></span>
                    {displayName(waveformId)}
                  </button>
                  <Select
                    class="-ml-px w-28 rounded-l-none rounded-r-full"
                    value={editingWaveform.type}
                    options={WAVEFORM_TYPES}
                    formatLabel={(type) => WAVEFORM_TYPE_LABELS[type]}
                    disabled={!canEdit}
                    onChange={changeWaveformType}
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
            <div class="border-t bg-tint">
              {#if isDerivedWaveform(waveform)}
                <div class="inspector-body px-4 py-3">
                  <div class="property-row">
                    <h3 class="text-xs font-semibold tracking-wider text-fg-muted uppercase">Derived</h3>
                    <div class="property-controls">
                      <Select
                        prefix="Operation"
                        class="w-full"
                        value={waveform.operation}
                        options={DERIVED_OPERATIONS}
                        formatLabel={displayName}
                        disabled={!canEdit}
                        onChange={changeDerivedOperation}
                      />
                      <Select
                        prefix="Source"
                        class="w-full"
                        value={waveform.source}
                        options={derivedSources}
                        formatLabel={displayName}
                        disabled={!canEdit}
                        onChange={changeDerivedSource}
                      />
                      {#if waveform.operation === 'scale'}
                        <SpinBox
                          value={waveform.factor}
                          onChange={(value) => updateEditingField('factor', value)}
                          step={0.05}
                          prefix="Factor"
                          size="sm"
                          disabled={!canEdit}
                          class="w-full"
                        />
                      {:else if waveform.operation === 'offset'}
                        <SpinBox
                          value={waveform.delta}
                          onChange={(value) => updateEditingField('delta', value)}
                          step={0.01}
                          prefix="Delta"
                          suffix="V"
                          size="sm"
                          disabled={!canEdit}
                          class="w-full"
                        />
                      {:else if waveform.operation === 'shift'}
                        <SpinBox
                          value={waveform.fraction}
                          onChange={(value) => updateEditingField('fraction', value)}
                          min={0}
                          max={1}
                          step={0.01}
                          prefix="Fraction"
                          size="sm"
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
                        class="w-full"
                        value={windowMode}
                        options={['percent', 'seconds']}
                        formatLabel={displayName}
                        disabled={!canEdit}
                        onChange={(mode) => (windowMode = mode)}
                      />
                      <SpinBox
                        value={windowMode === 'percent' ? waveform.window.min : waveform.window.min * duration}
                        onChange={(value) =>
                          updateWindow('min', windowMode === 'percent' ? value : duration > 0 ? value / duration : 0)}
                        min={0}
                        max={windowMode === 'percent' ? waveform.window.max : waveform.window.max * duration}
                        step={windowMode === 'percent' ? 0.001 : 0.0001}
                        bigStep={windowMode === 'percent' ? 0.05 : 0.001}
                        prefix="Start"
                        suffix={windowMode === 'seconds' ? 's' : undefined}
                        size="sm"
                        disabled={!canEdit || (windowMode === 'seconds' && duration <= 0)}
                        class="w-full"
                      />
                      <SpinBox
                        value={windowMode === 'percent' ? waveform.window.max : waveform.window.max * duration}
                        onChange={(value) =>
                          updateWindow('max', windowMode === 'percent' ? value : duration > 0 ? value / duration : 0)}
                        min={windowMode === 'percent' ? waveform.window.min : waveform.window.min * duration}
                        max={windowMode === 'percent' ? 1 : duration}
                        step={windowMode === 'percent' ? 0.001 : 0.0001}
                        bigStep={windowMode === 'percent' ? 0.05 : 0.001}
                        prefix="End"
                        suffix={windowMode === 'seconds' ? 's' : undefined}
                        size="sm"
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
                        class="w-full"
                        value={voltageMode}
                        options={['minmax', 'ampoffset']}
                        formatLabel={(mode) => (mode === 'minmax' ? 'Min / Max' : 'Amp / Offset')}
                        disabled={!canEdit}
                        onChange={(mode) => (voltageMode = mode)}
                      />
                      <SpinBox
                        value={voltageMode === 'minmax'
                          ? waveform.voltage.min
                          : (waveform.voltage.max - waveform.voltage.min) / 2}
                        onChange={voltageMode === 'minmax' ? (value) => updateVoltage('min', value) : updateAmplitude}
                        min={voltageMode === 'minmax' ? voltageRange?.min : 0}
                        max={voltageMode === 'minmax' ? waveform.voltage.max : undefined}
                        step={0.001}
                        prefix={voltageMode === 'minmax' ? 'Min' : 'Amp'}
                        suffix="V"
                        size="sm"
                        disabled={!canEdit}
                        class="w-full"
                      />
                      <SpinBox
                        value={voltageMode === 'minmax'
                          ? waveform.voltage.max
                          : (waveform.voltage.max + waveform.voltage.min) / 2}
                        onChange={voltageMode === 'minmax' ? (value) => updateVoltage('max', value) : updateOffset}
                        min={voltageMode === 'minmax' ? waveform.voltage.min : voltageRange?.min}
                        max={voltageRange?.max}
                        step={0.001}
                        prefix={voltageMode === 'minmax' ? 'Max' : 'Offset'}
                        suffix="V"
                        size="sm"
                        disabled={!canEdit}
                        class="w-full"
                      />
                      <SpinBox
                        value={waveform.rest_voltage ?? waveform.voltage.min}
                        onChange={(value) => updateEditingField('rest_voltage', value)}
                        min={waveform.voltage.min}
                        max={waveform.voltage.max}
                        step={0.001}
                        home={() => waveform.voltage.min}
                        prefix="Rest"
                        suffix="V"
                        size="sm"
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
                          class="w-full"
                          value={repeatMode}
                          options={['cycles', 'frequency']}
                          formatLabel={displayName}
                          disabled={!canEdit}
                          onChange={(mode) => (repeatMode = mode)}
                        />
                        <label class="min-w-0">
                          <span class="sr-only">{repeatMode === 'cycles' ? 'Cycles' : 'Frequency'}</span>
                          <SpinBox
                            value={repeatMode === 'cycles' ? cycleCount : cycleFrequency}
                            onChange={repeatMode === 'cycles' ? updateCycleCount : updateCycleFrequency}
                            min={0.001}
                            step={repeatMode === 'cycles' ? 0.25 : 0.01}
                            suffix={repeatMode === 'frequency' ? 'Hz' : undefined}
                            size="sm"
                            disabled={!canEdit || (repeatMode === 'frequency' && activeWindowSeconds <= 0)}
                            class="w-full"
                          />
                        </label>
                        {#if waveform.type === 'square'}
                          <SpinBox
                            value={waveform.duty_cycle}
                            onChange={(value) => updateEditingField('duty_cycle', value)}
                            min={0}
                            max={1}
                            step={0.001}
                            prefix="Duty"
                            size="sm"
                            disabled={!canEdit}
                            class="w-full"
                          />
                        {:else if waveform.type === 'triangle' || waveform.type === 'sawtooth'}
                          <SpinBox
                            value={waveform.symmetry ?? 1}
                            onChange={(value) => updateEditingField('symmetry', value)}
                            min={0}
                            max={1}
                            step={0.001}
                            prefix="Symmetry"
                            size="sm"
                            disabled={!canEdit}
                            class="w-full"
                          />
                        {/if}
                        <SpinBox
                          value={(waveform.phase ?? 0) * (180 / Math.PI)}
                          onChange={(value) => updateEditingField('phase', value * (Math.PI / 180))}
                          step={0.01}
                          prefix="Phase"
                          suffix="deg"
                          size="sm"
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
        </div>
      {/each}

      {#if groups.length === 0}
        <div class="flex min-h-56 items-center justify-center text-lg text-fg-muted">No synchronized outputs</div>
      {/if}
    </div>
  </div>
  <footer
    class="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-t border-line-muted bg-shell px-4 py-2"
    aria-labelledby="timing-heading"
  >
    <h2 id="timing-heading" class="shrink-0 text-sm text-fg-muted">Timing</h2>
    <div class="flex min-w-0 flex-[1_1_32rem] flex-wrap items-center gap-2">
      <NumberBox
        value={duration * 1000}
        onChange={(value) => updateTiming('duration', value / 1000)}
        min={0.1}
        step={0.1}
        bigStep={1}
        prefix="Active"
        suffix="ms"
        size="sm"
        disabled={!canEdit}
        class="min-w-36 flex-1"
      />
      <NumberBox
        value={restTime * 1000}
        onChange={(value) => updateTiming('rest_time', value / 1000)}
        min={0}
        step={0.1}
        bigStep={1}
        prefix="Rest"
        suffix="ms"
        size="sm"
        disabled={!canEdit}
        class="min-w-36 flex-1"
      />
      <NumberBox
        value={sampleRate / 1000}
        onChange={(value) => updateTiming('sample_rate', value * 1000)}
        min={0.001}
        step={0.001}
        bigStep={1}
        prefix="Sample rate"
        suffix="kHz"
        size="sm"
        disabled={!canEdit}
        class="min-w-52 flex-1"
      />
    </div>
  </footer>
{:else}
  <PageFallback items={[profileItem, { label: displayName(selectedGeneratorUid) }]}>
    Generator “{displayName(selectedGeneratorUid)}” is not configured for this profile.
  </PageFallback>
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
