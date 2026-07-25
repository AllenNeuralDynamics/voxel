<script lang="ts">
  import { Collapsible } from 'bits-ui';
  import { watch } from 'runed';
  import { SvelteSet } from 'svelte/reactivity';
  import { toast } from 'svelte-sonner';

  import { resolveDeviceColor, waveformPortColor } from '$lib/colors.svelte';
  import { ChevronDown, Close } from '$lib/icons';
  import { Button, Select } from '$lib/kit';
  import type { SelectOption } from '$lib/kit/Select.svelte';
  import type { DerivedWaveform, Signals, Waveform } from '$lib/model';
  import { getVoxelApp } from '$lib/model';
  import { SpinBox } from '$lib/prop/numeric';
  import { sanitizeString, toastError } from '$lib/utils';

  import WaveformPanel from './WaveformPanel.svelte';
  import { generateTraces, isDerivedWaveform, resolveWaveforms } from './waveforms';

  // ──────────────────────────────── Session wiring ────────────────────────────────

  const app = getVoxelApp();
  const instrument = $derived(app.instrument);
  const canEdit = $derived(instrument?.mode !== 'capture');

  const profile = $derived(instrument ? instrument.imaging.profiles[instrument.activeProfileId] : undefined);

  // ──────────────────────────────── Constants (pure) ────────────────────────────────

  /** Fixed height of the plot area (Collapsible.Content) when a panel is expanded.
   *  Row total ≈ row padding + header (intrinsic) + plotAreaHeight. */
  const plotAreaHeight = 120;
  // Fallback Y range when a channel has no resolved waveform yet.
  const DEFAULT_YRANGE = { min: 0, max: 1 };

  const WAVEFORM_TYPE_DEFAULTS: Record<string, Record<string, unknown>> = {
    pulse: {},
    square: { duty_cycle: 0.5 },
    sine: { cycles: 1, phase: 0 },
    triangle: { cycles: 1, symmetry: 1.0 }
  };

  const waveformTypeOptions: SelectOption[] = [
    { value: 'pulse', label: 'Pulse' },
    { value: 'square', label: 'Square' },
    { value: 'sine', label: 'Sine' },
    { value: 'triangle', label: 'Triangle' },
    { value: 'multi_point', label: 'Multi-point' },
    { value: 'csv', label: 'CSV' },
    { value: 'derived', label: 'Derived' }
  ];

  const derivedOpOptions: SelectOption[] = [
    { value: 'mirror', label: 'Mirror' },
    { value: 'scale', label: 'Scale' },
    { value: 'offset', label: 'Offset' },
    { value: 'shift', label: 'Shift' }
  ];

  interface Timing {
    sample_rate: number;
    duration: number;
    rest_time: number;
  }

  const defaultTiming: Timing = {
    sample_rate: 100000,
    duration: 0.01,
    rest_time: 0
  };

  // ──────────────────────────────── Pure helpers ────────────────────────────────

  function cloneWaveform(wf: Waveform): Waveform {
    return structuredClone($state.snapshot(wf)) as Waveform;
  }

  /**
   * Build a new waveform of ``newType`` derived from ``source``. Primitive→primitive
   * copies voltage/window; primitive→derived picks the first sibling as ``source``
   * channel; derived→primitive resolves the source to seed voltage/window.
   */
  function changeWaveformType(
    current: Waveform,
    newType: string,
    siblingsForDerived: Record<string, Waveform>,
    siblingKey: string
  ): Waveform | null {
    if (newType === 'derived') {
      const candidates = Object.keys(siblingsForDerived).filter((k) => k !== siblingKey);
      const src = candidates[0] ?? siblingKey;
      return { type: 'derived', operation: 'mirror', source: src };
    }
    const extra = WAVEFORM_TYPE_DEFAULTS[newType];
    if (extra === undefined) return null;

    let voltage: { min: number; max: number };
    let window: { min: number; max: number };
    let rest_voltage: number | undefined;

    if (isDerivedWaveform(current)) {
      const resolved = resolveWaveforms(siblingsForDerived)[siblingKey];
      if (resolved) {
        voltage = { min: resolved.voltage.min, max: resolved.voltage.max };
        window = { min: resolved.window.min, max: resolved.window.max };
        rest_voltage = resolved.rest_voltage;
      } else {
        voltage = { min: 0, max: 1 };
        window = { min: 0, max: 1 };
      }
    } else {
      voltage = { min: current.voltage.min, max: current.voltage.max };
      window = { min: current.window.min, max: current.window.max };
      rest_voltage = current.rest_voltage;
    }

    return { type: newType, voltage, window, rest_voltage, ...extra } as Waveform;
  }

  // ──────────────────────────────── Signal-generator tab state ────────────────────────────────

  /** All signal generators referenced by this profile's sync block. */
  const generatorUids = $derived<string[]>(profile ? Object.keys(profile.sync) : []);

  /** Options for the signal-generator <Select>. Maps each uid to a display label. */
  const generatorOptions = $derived<SelectOption[]>(
    generatorUids.map((uid) => ({ value: uid, label: sanitizeString(uid) }))
  );

  /** Currently selected signal-generator tab. Defaults to the first uid once available. */
  let selectedGeneratorUid = $state<string | null>(null);

  watch(
    () => generatorUids,
    (uids) => {
      if (uids.length === 0) {
        selectedGeneratorUid = null;
        return;
      }
      if (!selectedGeneratorUid || !uids.includes(selectedGeneratorUid)) {
        selectedGeneratorUid = uids[0];
      }
    }
  );

  // ──────────────────────────────── Source of truth (streamed loaded + config) ────────────────────────────────

  const loadedSignals = $derived.by<Signals | null>(() => {
    if (!selectedGeneratorUid) return null;
    return instrument?.signalGenerators.get(selectedGeneratorUid)?.loaded ?? null;
  });

  const configSignals = $derived.by<Signals | null>(() => {
    if (!profile || !selectedGeneratorUid) return null;
    return profile.sync[selectedGeneratorUid] ?? null;
  });

  /**
   * Base set of waveforms shown on the plot. /tune is an oscilloscope-style view: the
   * plot renders strictly what the hardware is currently emitting (``loaded``). The
   * profile config is used only as the editor baseline + patch target, not for display —
   * so there is no config/loaded divergence when a patch is in flight.
   */
  const baseWaveforms = $derived.by<Record<string, Waveform>>(() => {
    return loadedSignals?.waveforms ?? {};
  });

  const voltageRange = $derived.by<{ min: number; max: number } | null>(() => {
    if (!selectedGeneratorUid) return null;
    return instrument?.signalGenerators.get(selectedGeneratorUid)?.voltageRange ?? null;
  });

  const generatorPorts = $derived.by<Record<string, string>>(() => {
    if (!selectedGeneratorUid) return {};
    const dev = instrument?.hal.devices[selectedGeneratorUid];
    const ports = dev?.init?.ports as Record<string, string> | undefined;
    return ports ?? {};
  });

  // ──────────────────────────────── Waveform devices ────────────────────────────────

  /** Device ids that have a waveform entry in the current generator tab's signals.
   *  Real devices in the active profile come first (in profile-discovery order); pure DAQ
   *  port labels (no backing Device) appear after, in waveform-key order. */
  const tabWaveformIds = $derived.by<string[]>(() => {
    const names = Object.keys(baseWaveforms);
    const ordered: string[] = [];
    for (const id of instrument?.roles.keys() ?? []) {
      if (names.includes(id)) ordered.push(id);
    }
    for (const id of names) if (!ordered.includes(id)) ordered.push(id);
    return ordered;
  });

  /** Per-channel color: devices in the active profile get their role accent (from `instrument.roles`);
   *  pure DAQ port labels get reverse-indexed entries from the waveform palette so the pools don't collide. */
  const waveformColors = $derived.by<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    let portIdx = 0;
    for (const id of tabWaveformIds) {
      const role = instrument?.roles.get(id);
      const emission = instrument?.activeChannels.find((ch) => ch.camera.id === id || ch.laser.id === id)?.emission;
      const accent = role ? resolveDeviceColor(role, emission) : undefined;
      out[id] = accent ?? waveformPortColor(portIdx++);
    }
    return out;
  });

  // ──────────────────────────────── Panel grouping ────────────────────────────────
  //
  // A "panel" is a visual grouping of one-or-more channels sharing a plot. Default
  // grouping: each primitive waveform forms a panel with any derived waveforms that
  // reference it as their source. Derived waveforms whose source is absent from the
  // tab stand alone. Manual merge/split UI deferred to a later PR.

  interface Panel {
    channels: string[];
  }

  const panels = $derived.by<Panel[]>(() => {
    const claimed = new SvelteSet<string>();
    const result: Panel[] = [];
    // First pass: primitives collect their derivers.
    for (const id of tabWaveformIds) {
      if (claimed.has(id)) continue;
      const wf = baseWaveforms[id];
      if (!wf || isDerivedWaveform(wf)) continue;
      const derivers = tabWaveformIds.filter((other) => {
        const d = baseWaveforms[other];
        return d && isDerivedWaveform(d) && d.source === id;
      });
      result.push({ channels: [id, ...derivers] });
      claimed.add(id);
      derivers.forEach((d) => claimed.add(d));
    }
    // Leftover (e.g., derived waveforms whose source isn't in the tab) → standalone.
    for (const id of tabWaveformIds) {
      if (!claimed.has(id)) result.push({ channels: [id] });
    }
    return result;
  });

  /** Union of voltage ranges for all channels in a panel. */
  function panelYRange(channels: string[]): { min: number; max: number } {
    let min = Infinity;
    let max = -Infinity;
    for (const c of channels) {
      const r = resolved[c];
      if (!r?.voltage) continue;
      min = Math.min(min, r.voltage.min);
      max = Math.max(max, r.voltage.max);
    }
    if (!isFinite(min) || !isFinite(max)) return DEFAULT_YRANGE;
    return { min, max };
  }

  /** Per-panel collapse state (session-only). Key is ``panel.channels.join(',')``. */
  const collapsedPanels = new SvelteSet<string>();

  // ──────────────────────────────── Waveform editing (per-channel lock) ────────────────────────────────

  let selectedDeviceId = $state<string | null>(null);
  let editingWaveform = $state<Waveform | null>(null);

  type VoltageMode = 'minmax' | 'ampoffset';
  let voltageMode = $state<VoltageMode>('minmax');

  type WindowMode = 'percent' | 'seconds';
  let windowMode = $state<WindowMode>('seconds');

  type RepeatMode = 'cycles' | 'frequency';
  let repeatMode = $state<RepeatMode>('cycles');

  /** Select a waveform for editing. Clicking the selected waveform again closes
   *  the inspector, while switching selection first flushes any pending edit. */
  function selectDevice(deviceId: string) {
    if (deviceId === selectedDeviceId) {
      deselectDevice();
      return;
    }
    const source = baseWaveforms[deviceId];
    if (!source) return;
    flushPendingPatch();
    selectedDeviceId = deviceId;
    editingWaveform = cloneWaveform(source);
  }

  function deselectDevice() {
    flushPendingPatch();
    selectedDeviceId = null;
    editingWaveform = null;
  }

  // Selection is optional. Clear it if its waveform disappears, but do not
  // automatically open the inspector when a generator tab becomes available.
  watch(
    () => tabWaveformIds,
    (ids) => {
      if (selectedDeviceId && !ids.includes(selectedDeviceId)) {
        discardPendingPatch();
        selectedDeviceId = null;
        editingWaveform = null;
      }
    }
  );

  /** Merge the user's in-flight edit over the base waveforms for plotting + resolution. */
  const displayWaveforms = $derived.by<Record<string, Waveform>>(() => {
    if (!selectedDeviceId || !editingWaveform) return baseWaveforms;
    return { ...baseWaveforms, [selectedDeviceId]: editingWaveform };
  });

  // ──────────────────────────────── Timing (commit-based autosave) ────────────────────────────────

  let localTiming = $state<Timing>({ ...defaultTiming });
  let timingCommitTimer: ReturnType<typeof setTimeout> | null = null;
  let timingCommitInFlight = false;
  let timingHasLocalChanges = false;
  let timingRevision = 0;

  function syncLocalTiming(signals: Signals | null) {
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
      if (!timingHasLocalChanges) syncLocalTiming(signals);
    }
  );

  watch(
    () => `${instrument?.activeProfileId ?? ''}:${selectedGeneratorUid ?? ''}`,
    () => {
      if (timingCommitTimer) clearTimeout(timingCommitTimer);
      timingCommitTimer = null;
      timingHasLocalChanges = false;
      timingRevision += 1;
      syncLocalTiming(configSignals);
    },
    { lazy: true }
  );

  function scheduleTimingCommit() {
    if (timingCommitTimer) clearTimeout(timingCommitTimer);
    timingCommitTimer = setTimeout(() => {
      timingCommitTimer = null;
      void commitTiming();
    }, 150);
  }

  function updateTimingField(field: 'sample_rate' | 'duration' | 'rest_time', value: number) {
    if (!isFinite(value)) return;
    localTiming = { ...localTiming, [field]: value };
    timingHasLocalChanges = true;
    timingRevision += 1;
    scheduleTimingCommit();
  }

  async function commitTiming() {
    if (timingCommitInFlight) {
      scheduleTimingCommit();
      return;
    }
    if (!canEdit || !timingHasLocalChanges || !selectedGeneratorUid || !configSignals) return;

    const generatorUid = selectedGeneratorUid;
    const revision = timingRevision;
    const next: Signals = {
      sample_rate: localTiming.sample_rate,
      duration: localTiming.duration,
      rest_time: localTiming.rest_time,
      waveforms: configSignals.waveforms
    };

    timingCommitInFlight = true;
    try {
      await instrument?.updateSignals(generatorUid, next);
      if (selectedGeneratorUid === generatorUid && timingRevision === revision) {
        timingHasLocalChanges = false;
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update timing');
      if (selectedGeneratorUid === generatorUid && timingRevision === revision) {
        timingHasLocalChanges = false;
        syncLocalTiming(configSignals);
      }
    } finally {
      timingCommitInFlight = false;
      if (timingHasLocalChanges && timingRevision !== revision) scheduleTimingCommit();
    }
  }

  $effect(() => {
    return () => {
      if (timingCommitTimer) clearTimeout(timingCommitTimer);
    };
  });

  // ──────────────────────────────── Derived timing values ────────────────────────────────

  const duration = $derived(localTiming.duration ?? 0);
  const restTime = $derived(localTiming.rest_time ?? 0);
  const sampleRate = $derived(localTiming.sample_rate ?? 0);
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

  /** Trace samples + resolved (derived→primitive) waveforms, shared across all rows.
   *  Each ``waveformRow`` snippet reads its own slice (``plotData.traces[id]`` /
   *  ``resolved[id]``). Regenerates whenever any tracked waveform field changes. */
  const plotData = $derived(generateTraces(displayWaveforms, duration, restTime));
  const resolved = $derived(resolveWaveforms(displayWaveforms));

  // ──────────────────────────────── Auto-load waveform edits (debounced) ────────────────────────────────

  /**
   * Serializable fingerprint of the editing waveform. ``watch`` on this fires only
   * when the user actually mutates a field (not just on reference identity).
   */
  const editFingerprint = $derived.by<string | null>(() => {
    if (!selectedDeviceId || !editingWaveform) return null;
    return JSON.stringify({ id: selectedDeviceId, wf: $state.snapshot(editingWaveform) });
  });

  interface PendingWaveformPatch {
    generatorUid: string;
    channelId: string;
    waveform: Waveform;
    base: Signals;
  }

  let pendingPatchTimer: ReturnType<typeof setTimeout> | null = null;
  let pendingPatch: PendingWaveformPatch | null = null;

  function sendWaveformPatch(patch: PendingWaveformPatch) {
    const merged: Signals = {
      sample_rate: patch.base.sample_rate,
      duration: patch.base.duration,
      rest_time: patch.base.rest_time,
      waveforms: { ...patch.base.waveforms, [patch.channelId]: patch.waveform }
    };
    toastError(instrument?.updateSignals(patch.generatorUid, merged));
  }

  function discardPendingPatch() {
    if (pendingPatchTimer) clearTimeout(pendingPatchTimer);
    pendingPatchTimer = null;
    pendingPatch = null;
  }

  function flushPendingPatch() {
    if (pendingPatchTimer) clearTimeout(pendingPatchTimer);
    pendingPatchTimer = null;
    const patch = pendingPatch;
    pendingPatch = null;
    if (patch) sendWaveformPatch(patch);
  }

  watch(
    () => editFingerprint,
    (fp) => {
      if (!fp || !canEdit || !selectedGeneratorUid || !configSignals || !editingWaveform || !selectedDeviceId) {
        discardPendingPatch();
        return;
      }
      if (pendingPatchTimer) clearTimeout(pendingPatchTimer);
      pendingPatch = {
        generatorUid: selectedGeneratorUid,
        channelId: selectedDeviceId,
        waveform: cloneWaveform(editingWaveform),
        base: configSignals
      };

      pendingPatchTimer = setTimeout(() => {
        pendingPatchTimer = null;
        const patch = pendingPatch;
        pendingPatch = null;
        if (patch) sendWaveformPatch(patch);
      }, 150);

      return () => {
        if (pendingPatchTimer) {
          clearTimeout(pendingPatchTimer);
          pendingPatchTimer = null;
        }
      };
    },
    { lazy: true }
  );

  // ──────────────────────────────── Waveform mutation helpers ────────────────────────────────

  function updateEditingField(field: string, value: unknown) {
    if (!editingWaveform) return;
    if (typeof value === 'number' && !isFinite(value)) return;
    (editingWaveform as unknown as Record<string, unknown>)[field] = value;
  }

  function setEditingVoltage(key: 'min' | 'max', value: number) {
    if (!editingWaveform || isDerivedWaveform(editingWaveform) || !isFinite(value)) return;
    if (voltageRange) value = Math.max(voltageRange.min, Math.min(voltageRange.max, value));
    editingWaveform.voltage[key] = value;
    const rest = editingWaveform.rest_voltage ?? 0;
    editingWaveform.rest_voltage = Math.max(editingWaveform.voltage.min, Math.min(editingWaveform.voltage.max, rest));
  }

  function setEditingAmplitude(amplitude: number) {
    if (!editingWaveform || isDerivedWaveform(editingWaveform) || !isFinite(amplitude)) return;
    const offset = (editingWaveform.voltage.max + editingWaveform.voltage.min) / 2;
    const amp = Math.max(0, amplitude);
    setEditingVoltage('min', offset - amp);
    setEditingVoltage('max', offset + amp);
  }

  function setEditingOffset(offset: number) {
    if (!editingWaveform || isDerivedWaveform(editingWaveform) || !isFinite(offset)) return;
    const amp = (editingWaveform.voltage.max - editingWaveform.voltage.min) / 2;
    setEditingVoltage('min', offset - amp);
    setEditingVoltage('max', offset + amp);
  }

  function updateEditingWindow(key: 'min' | 'max', value: number) {
    if (!editingWaveform || isDerivedWaveform(editingWaveform) || !isFinite(value)) return;
    editingWaveform.window[key] = value;
  }

  function updateCycleCount(value: number) {
    updateEditingField('cycles', value);
    updateEditingField('frequency', null);
  }

  function updateCycleFrequency(value: number) {
    if (activeWindowSeconds <= 0) return;
    updateEditingField('cycles', value * activeWindowSeconds);
    updateEditingField('frequency', null);
  }

  function changeEditingType(newType: string) {
    if (!editingWaveform || !selectedDeviceId) return;
    const result = changeWaveformType(editingWaveform, newType, baseWaveforms, selectedDeviceId);
    if (result) editingWaveform = result;
  }

  function changeDerivedOperation(op: string) {
    if (!editingWaveform || !isDerivedWaveform(editingWaveform)) return;
    const source = editingWaveform.source;
    switch (op) {
      case 'mirror':
        editingWaveform = { type: 'derived', operation: 'mirror', source };
        break;
      case 'scale':
        editingWaveform = { type: 'derived', operation: 'scale', source, factor: 1 };
        break;
      case 'offset':
        editingWaveform = { type: 'derived', operation: 'offset', source, delta: 0 };
        break;
      case 'shift':
        editingWaveform = { type: 'derived', operation: 'shift', source, fraction: 0 };
        break;
    }
  }

  function changeDerivedSource(src: string) {
    if (!editingWaveform || !isDerivedWaveform(editingWaveform)) return;
    (editingWaveform as DerivedWaveform).source = src;
  }

  const derivedSourceOptions = $derived.by<SelectOption[]>(() => {
    if (!selectedDeviceId) return [];
    return Object.keys(baseWaveforms)
      .filter((k) => k !== selectedDeviceId)
      .map((k) => ({ value: k, label: sanitizeString(k) }));
  });

  // ──────────────────────────────── Plot context (bundled chrome for WaveformPanel) ────────────────────────────────

  /** Device-wide chrome shared by every ``WaveformPanel`` on the page. Panels are
   *  self-sizing (internal ``ResizeObserver``), so layout dimensions aren't here. */
  const plotContext = $derived<import('./WaveformPanel.svelte').PlotContext>({
    duration,
    restTime,
    voltageRange,
    syncKey: 'tune'
  });
</script>

{#if profile}
  <div class="flex h-full flex-col">
    <!-- Top bar: signal-generator selector + directly editable generator timing. -->
    <div class="flex shrink-0 items-center gap-2 border-b px-4 py-1.5 pb-2">
      <div class="flex w-36 shrink-0 flex-col gap-1" role="group" aria-label="Signal generator">
        <span class="px-1 text-sm font-medium text-fg-muted">Generator</span>
        <Select
          size="xs"
          class="w-full"
          value={selectedGeneratorUid ?? ''}
          options={generatorOptions}
          disabled={generatorOptions.length === 0}
          onchange={(v) => (selectedGeneratorUid = v)}
        />
      </div>
      <div class="ml-auto flex items-center gap-2" role="group" aria-label="Clock timing">
        <label class="flex flex-col gap-1">
          <span class="px-1 text-sm font-medium text-fg-muted">Sample rate</span>
          <SpinBox
            model={{
              value: sampleRate / 1000,
              onChange: (v) => updateTimingField('sample_rate', v * 1000),
              min: 1,
              step: 0.001,
              bigStep: 1
            }}
            suffix=" kHz"
            size="xs"
            numCharacters={4}
            align="right"
            steppers={false}
            disabled={!canEdit}
            class="w-24"
          />
        </label>
        <label class="flex flex-col gap-1">
          <span class="px-1 text-sm font-medium text-fg-muted">Active</span>
          <SpinBox
            model={{
              value: duration * 1000,
              onChange: (v) => updateTimingField('duration', v / 1000),
              min: 0.1,
              step: 0.1,
              bigStep: 1
            }}
            suffix=" ms"
            size="xs"
            numCharacters={5}
            align="right"
            steppers={false}
            disabled={!canEdit}
            class="w-24"
          />
        </label>
        <label class="flex flex-col gap-1">
          <span class="px-1 text-sm font-medium text-fg-muted">Rest</span>
          <SpinBox
            model={{
              value: restTime * 1000,
              onChange: (v) => updateTimingField('rest_time', v / 1000),
              min: 0,
              step: 0.1,
              bigStep: 1
            }}
            suffix=" ms"
            size="xs"
            numCharacters={5}
            align="right"
            steppers={false}
            disabled={!canEdit}
            class="w-24"
          />
        </label>
      </div>
    </div>
    <div class="min-h-0 flex-1 pb-4">
      <div class="flex h-full [scroll-snap-type:y_mandatory] flex-col gap-3 overflow-y-auto p-4">
        {#each panels as panel (panel.channels.join(','))}
          {@const yRange = panelYRange(panel.channels)}
          {@const colors = panel.channels.map((ch) => waveformColors[ch] ?? '#888')}
          {@const voltages = panel.channels.map((ch) => plotData.traces[ch] ?? [])}
          {@const panelKey = panel.channels.join(',')}
          {@const isOpen = !collapsedPanels.has(panelKey)}
          <Collapsible.Root
            open={isOpen}
            onOpenChange={(o) => (o ? collapsedPanels.delete(panelKey) : collapsedPanels.add(panelKey))}
          >
            <div class="row flex w-full shrink-0 snap-end flex-col rounded-md border border-border p-2">
              <div class="flex items-center gap-1 px-1 text-base text-fg-muted">
                {#each panel.channels as channelId (channelId)}
                  {@const color = waveformColors[channelId] ?? '#888'}
                  <button
                    type="button"
                    onclick={() => {
                      selectDevice(channelId);
                      collapsedPanels.delete(panelKey);
                    }}
                    class="flex cursor-pointer items-center gap-1.5 rounded-full border px-2 py-0.5 transition-colors
                        {channelId === selectedDeviceId ? 'border-border bg-element-selected' : 'border-transparent'}"
                  >
                    <span class="h-2 w-2 shrink-0 rounded-full" style="background-color: {color};" aria-hidden="true">
                    </span>
                    <span class="text-fg">{sanitizeString(channelId)}</span>
                  </button>
                {/each}
                <Collapsible.Trigger
                  class="ml-auto cursor-pointer rounded p-0.5 text-fg-muted transition-colors hover:bg-element-hover hover:text-fg"
                  aria-label={isOpen ? 'Collapse panel' : 'Expand panel'}
                >
                  <ChevronDown class="transition-transform {isOpen ? '' : '-rotate-90'}" width="14" height="14" />
                </Collapsible.Trigger>
              </div>
              <Collapsible.Content
                forceMount
                class="overflow-hidden transition-[height] duration-150"
                style="height: {isOpen ? `${plotAreaHeight}px` : '0'};"
              >
                <WaveformPanel time={plotData.time} {voltages} {colors} {yRange} context={plotContext} />
              </Collapsible.Content>
            </div>
          </Collapsible.Root>
        {/each}
        {#if panels.length === 0}
          <div class="flex h-full items-center justify-center text-lg text-fg-muted">No waveform data</div>
        {/if}
      </div>
    </div>
    {#if selectedDeviceId && editingWaveform}
      {@const deviceId = selectedDeviceId}
      {@const waveform = editingWaveform}
      {@const color = waveformColors[selectedDeviceId] ?? '#888'}
      {@const port = generatorPorts[selectedDeviceId]}
      <section class="shrink-0 rounded-t-xl border-t-2 bg-canvas" aria-label="Waveform inspector">
        <div class="flex items-center gap-2 border-b py-2 pr-3 pl-4">
          <div class="flex min-w-0 items-center gap-2 font-medium">
            <span class="h-2.5 w-2.5 shrink-0 rounded-full" style="background-color: {color};" aria-hidden="true"
            ></span>
            <span class="truncate">{sanitizeString(deviceId)}</span>
            {#if port}<span class="shrink-0 text-fg-faint">({port})</span>{/if}
          </div>
          <Select
            prefix="Type"
            size="xs"
            class="ml-auto w-44"
            value={waveform.type}
            options={waveformTypeOptions}
            disabled={!canEdit}
            onchange={changeEditingType}
          />
          {#if !canEdit}
            <span class="text-sm text-warning/80">Acquiring — controls are read-only.</span>
          {/if}
          <Button
            variant="ghost"
            size="icon-xs"
            onclick={deselectDevice}
            title="Close waveform inspector"
            aria-label="Close waveform inspector"
          >
            <Close width="14" height="14" />
          </Button>
        </div>

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
                  options={derivedOpOptions}
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
                    numCharacters={6}
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
                    numCharacters={6}
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
                    numCharacters={6}
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
                {#if windowMode === 'percent'}
                  <SpinBox
                    model={{
                      value: waveform.window.min,
                      onChange: (value) => updateEditingWindow('min', value),
                      min: 0,
                      max: waveform.window.max,
                      step: 0.001,
                      bigStep: 0.05
                    }}
                    prefix="Start"
                    size="xs"
                    numCharacters={5}
                    align="right"
                    disabled={!canEdit}
                    class="w-full"
                  />
                  <SpinBox
                    model={{
                      value: waveform.window.max,
                      onChange: (value) => updateEditingWindow('max', value),
                      min: waveform.window.min,
                      max: 1,
                      step: 0.001,
                      bigStep: 0.05
                    }}
                    prefix="End"
                    size="xs"
                    numCharacters={5}
                    align="right"
                    disabled={!canEdit}
                    class="w-full"
                  />
                {:else}
                  <SpinBox
                    model={{
                      value: waveform.window.min * duration,
                      onChange: (value) => updateEditingWindow('min', duration > 0 ? value / duration : 0),
                      min: 0,
                      max: waveform.window.max * duration,
                      step: 0.0001,
                      bigStep: 0.001
                    }}
                    prefix="Start"
                    suffix=" s"
                    size="xs"
                    numCharacters={6}
                    align="right"
                    disabled={!canEdit || duration <= 0}
                    class="w-full"
                  />
                  <SpinBox
                    model={{
                      value: waveform.window.max * duration,
                      onChange: (value) => updateEditingWindow('max', duration > 0 ? value / duration : 0),
                      min: waveform.window.min * duration,
                      max: duration,
                      step: 0.0001,
                      bigStep: 0.001
                    }}
                    prefix="End"
                    suffix=" s"
                    size="xs"
                    numCharacters={6}
                    align="right"
                    disabled={!canEdit || duration <= 0}
                    class="w-full"
                  />
                {/if}
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
                {#if voltageMode === 'minmax'}
                  <SpinBox
                    model={{
                      value: waveform.voltage.min,
                      onChange: (value) => setEditingVoltage('min', value),
                      min: voltageRange?.min,
                      max: waveform.voltage.max,
                      step: 0.005
                    }}
                    prefix="Min"
                    suffix=" V"
                    size="xs"
                    numCharacters={6}
                    align="right"
                    disabled={!canEdit}
                    class="w-full"
                  />
                  <SpinBox
                    model={{
                      value: waveform.voltage.max,
                      onChange: (value) => setEditingVoltage('max', value),
                      min: waveform.voltage.min,
                      max: voltageRange?.max,
                      step: 0.001
                    }}
                    prefix="Max"
                    suffix=" V"
                    size="xs"
                    numCharacters={6}
                    align="right"
                    disabled={!canEdit}
                    class="w-full"
                  />
                {:else}
                  <SpinBox
                    model={{
                      value: (waveform.voltage.max + waveform.voltage.min) / 2,
                      onChange: setEditingOffset,
                      min: voltageRange?.min,
                      max: voltageRange?.max,
                      step: 0.001
                    }}
                    prefix="Offset"
                    suffix=" V"
                    size="xs"
                    numCharacters={6}
                    align="right"
                    disabled={!canEdit}
                    class="w-full"
                  />
                  <SpinBox
                    model={{
                      value: (waveform.voltage.max - waveform.voltage.min) / 2,
                      onChange: setEditingAmplitude,
                      min: 0,
                      step: 0.001
                    }}
                    prefix="Amp"
                    suffix=" V"
                    size="xs"
                    numCharacters={6}
                    align="right"
                    disabled={!canEdit}
                    class="w-full"
                  />
                {/if}
                <SpinBox
                  model={{
                    value: waveform.rest_voltage ?? 0,
                    onChange: (value) => updateEditingField('rest_voltage', value),
                    min: waveform.voltage.min,
                    max: waveform.voltage.max,
                    step: 0.001,
                    home: () => waveform.voltage.min
                  }}
                  prefix="Rest"
                  suffix=" V"
                  size="xs"
                  numCharacters={6}
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
                    {#if repeatMode === 'cycles'}
                      <SpinBox
                        model={{
                          value: cycleCount,
                          onChange: updateCycleCount,
                          min: 0.001,
                          step: 0.25
                        }}
                        size="xs"
                        numCharacters={6}
                        align="right"
                        disabled={!canEdit}
                        class="w-full"
                      />
                    {:else}
                      <SpinBox
                        model={{
                          value: cycleFrequency,
                          onChange: updateCycleFrequency,
                          min: 0.001,
                          step: 0.01
                        }}
                        suffix=" Hz"
                        size="xs"
                        numCharacters={8}
                        align="right"
                        disabled={!canEdit || activeWindowSeconds <= 0}
                        class="w-full"
                      />
                    {/if}
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
                      numCharacters={6}
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
                        step: 0.0001
                      }}
                      prefix="Symmetry"
                      size="xs"
                      numCharacters={6}
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
                    numCharacters={6}
                    align="right"
                    disabled={!canEdit}
                    class="w-full"
                  />
                </div>
              </div>
            {/if}
          </div>
        {/if}
      </section>
    {/if}
  </div>
{:else}
  <div class="flex h-full items-center justify-center text-lg text-fg-muted">Select a profile to view waveforms</div>
{/if}

<style>
  .inspector-body {
    container-type: inline-size;
    max-height: 45vh;
    overflow-y: auto;
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
