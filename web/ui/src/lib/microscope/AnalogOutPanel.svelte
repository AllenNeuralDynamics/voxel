<script lang="ts">
  import type { Microscope } from '.';
  import { discoverProfileDevices } from './profile';
  import { generateTraces, niceTicks, resolveWaveforms, voltageRange } from '$lib/protocol/waveform';
  import type { AOSignals, ClockSource } from '$lib/protocol/session';
  import { isDerivedWaveform, type Waveform, type DerivedWaveform } from '$lib/protocol/waveform';
  import type { SelectOption } from '$lib/kit/Select.svelte';
  import { SpinBox, Select, Button } from '$lib/kit';
  import { cn, sanitizeString } from '$lib/utils';
  import { Check, Close } from '$lib/icons';
  import { toast } from 'svelte-sonner';
  import { watch } from 'runed';
  import { SvelteMap, SvelteSet } from 'svelte/reactivity';

  // ──────────────────────────────── Props ────────────────────────────────

  interface Props {
    microscope: Microscope;
    canEdit: boolean;
    class?: string;
  }

  let { microscope, canEdit, class: className }: Props = $props();

  // ──────────────────────────────── Top-level state ────────────────────────────────

  const profile = $derived(
    microscope.profiles.activeId ? microscope.config.profiles[microscope.profiles.activeId] : undefined
  );

  /** All AO devices referenced by this profile's sync block. */
  const aoUids = $derived<string[]>(profile ? Object.keys(profile.sync) : []);

  /** Currently selected AO tab. Defaults to the first AO uid once available. */
  let selectedAoUid = $state<string | null>(null);

  watch(
    () => aoUids,
    (uids) => {
      if (uids.length === 0) {
        selectedAoUid = null;
        return;
      }
      if (!selectedAoUid || !uids.includes(selectedAoUid)) {
        selectedAoUid = uids[0];
      }
    }
  );

  // Clear per-tab edit state when profile changes. Nothing to discard: waveform edits
  // auto-load on drag (so they're persisted), and timing edits have their own explicit
  // Apply button — if the user switches profiles with timing dirty, they implicitly
  // abandoned those changes.
  watch(
    () => microscope.profiles.activeId,
    () => {
      cancelEditing();
      timingDirty = false;
    },
    { lazy: true }
  );

  // ──────────────────────────────── Helpers: waveform defaults ────────────────────────────────

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
      // Pick any other channel as the initial source (or fall back to self — backend
      // will reject self-reference, which is the feedback we want).
      const candidates = Object.keys(siblingsForDerived).filter((k) => k !== siblingKey);
      const src = candidates[0] ?? siblingKey;
      return { type: 'derived', operation: 'mirror', source: src };
    }
    const extra = WAVEFORM_TYPE_DEFAULTS[newType];
    if (extra === undefined) return null;

    // Resolve voltage/window from current (primitive) or from the source it references (derived)
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

  function cloneWaveform(wf: Waveform): Waveform {
    return structuredClone($state.snapshot(wf)) as Waveform;
  }

  // ──────────────────────────────── Source of truth (streamed loaded + config) ────────────────────────────────

  /** Streamed ``AOSignals`` for the current AO tab, or ``null`` if hardware is fresh. */
  const loadedSignals = $derived.by<AOSignals | null>(() => {
    if (!selectedAoUid) return null;
    return microscope.analogOuts.get(selectedAoUid)?.loaded ?? null;
  });

  /** Profile config's copy of the AO signals — the edit baseline. */
  const configSignals = $derived.by<AOSignals | null>(() => {
    if (!profile || !selectedAoUid) return null;
    return profile.sync[selectedAoUid] ?? null;
  });

  /**
   * Base set of waveforms shown on the plot. Prefers the streamed ``loaded`` (hardware
   * truth) but falls back to the config copy for channels that aren't represented yet.
   */
  const baseWaveforms = $derived.by<Record<string, Waveform>>(() => {
    const fromLoaded = loadedSignals?.waveforms ?? {};
    const fromConfig = configSignals?.waveforms ?? {};
    return { ...fromConfig, ...fromLoaded };
  });

  /** Hardware AO voltage range for the selected AO tab. */
  const aoRange = $derived.by<{ min: number; max: number } | null>(() => {
    if (!selectedAoUid) return null;
    return microscope.analogOuts.get(selectedAoUid)?.voltageRange ?? null;
  });

  /** Physical port map (logical→PFI pin) pulled from the AO device's init block. */
  const aoPorts = $derived.by<Record<string, string>>(() => {
    if (!selectedAoUid) return {};
    const dev = microscope.config.rig.devices[selectedAoUid];
    const ports = dev?.init?.ports as Record<string, string> | undefined;
    return ports ?? {};
  });

  /** Logical trigger names defined on the AO device; drives the clock source dropdown. */
  const aoTriggers = $derived.by<Record<string, string>>(() => {
    if (!selectedAoUid) return {};
    const dev = microscope.config.rig.devices[selectedAoUid];
    const triggers = dev?.init?.triggers as Record<string, string> | undefined;
    return triggers ?? {};
  });

  const clockSourceOptions = $derived<SelectOption[]>([
    { value: '__internal__', label: 'Internal' },
    ...Object.entries(aoTriggers).map(([name, pin]) => ({
      value: name,
      label: `${sanitizeString(name)} (${pin})`
    }))
  ]);

  // ──────────────────────────────── Sidebar: waveform devices ────────────────────────────────

  const profileDevices = $derived(
    microscope.profiles.activeId ? discoverProfileDevices(microscope.config, microscope.profiles.activeId) : []
  );

  /** Device ids that have a waveform entry in the current AO tab's signals. */
  const tabWaveformIds = $derived.by<string[]>(() => {
    const names = Object.keys(baseWaveforms);
    // Preserve role-sorted order where possible, fall back to insertion order for unknowns
    const knownOrder = profileDevices.map((d) => d.id);
    const ordered: string[] = [];
    for (const id of knownOrder) if (names.includes(id)) ordered.push(id);
    for (const id of names) if (!ordered.includes(id)) ordered.push(id);
    return ordered;
  });

  const waveformColors = $derived<Record<string, string>>(
    Object.fromEntries(profileDevices.map((d) => [d.id, d.color]))
  );

  interface ChipGroup {
    parentId: string;
    children: string[];
  }

  const chipGroups = $derived.by<ChipGroup[]>(() => {
    const inTab = new Set(tabWaveformIds);
    const groups = new SvelteMap<string, ChipGroup>();
    const order: string[] = [];
    // First pass: primitives and derived-without-source-in-tab become parents
    for (const id of tabWaveformIds) {
      const wf = baseWaveforms[id];
      if (!wf) continue;
      if (isDerivedWaveform(wf) && inTab.has(wf.source)) continue;
      groups.set(id, { parentId: id, children: [] });
      order.push(id);
    }
    // Second pass: attach derived-with-source-in-tab to their parent
    for (const id of tabWaveformIds) {
      const wf = baseWaveforms[id];
      if (!wf) continue;
      if (isDerivedWaveform(wf) && inTab.has(wf.source)) {
        const parent = groups.get(wf.source);
        if (parent) parent.children.push(id);
      }
    }
    return order.map((id) => groups.get(id) as ChipGroup);
  });

  // ──────────────────────────────── Trace visibility ────────────────────────────────

  let hiddenDevices = new SvelteSet<string>();

  function toggleDeviceVisibility(deviceId: string) {
    if (hiddenDevices.has(deviceId)) hiddenDevices.delete(deviceId);
    else hiddenDevices.add(deviceId);
  }

  // ──────────────────────────────── Waveform editing (per-channel lock) ────────────────────────────────

  let selectedDeviceId = $state<string | null>(null);
  let editingWaveform = $state<Waveform | null>(null);

  type VoltageMode = 'minmax' | 'ampoffset';
  let voltageMode = $state<VoltageMode>('minmax');

  function selectDevice(deviceId: string) {
    if (!canEdit) return;
    const source = baseWaveforms[deviceId];
    if (!source) return;
    hiddenDevices.delete(deviceId);
    selectedDeviceId = deviceId;
    editingWaveform = cloneWaveform(source);
  }

  function cancelEditing() {
    selectedDeviceId = null;
    editingWaveform = null;
  }

  // Reset edit state whenever the AO tab changes
  watch(
    () => selectedAoUid,
    () => {
      cancelEditing();
    },
    { lazy: true }
  );

  /** Merge the user's in-flight edit over the base waveforms for plotting + resolution. */
  const displayWaveforms = $derived.by<Record<string, Waveform>>(() => {
    if (!selectedDeviceId || !editingWaveform) return baseWaveforms;
    return { ...baseWaveforms, [selectedDeviceId]: editingWaveform };
  });

  const editingIsDerived = $derived(editingWaveform != null && isDerivedWaveform(editingWaveform));

  // ──────────────────────────────── Timing (explicit Apply) ────────────────────────────────

  interface Timing {
    sample_rate: number;
    duration: number;
    rest_time: number;
    clock_src: ClockSource;
  }

  const defaultTiming: Timing = {
    sample_rate: 100000,
    duration: 0.01,
    rest_time: 0,
    clock_src: { type: 'internal' }
  };

  let localTiming = $state<Timing>({ ...defaultTiming });
  let timingDirty = $state(false);

  watch(
    () => configSignals,
    (signals) => {
      if (!signals) {
        localTiming = { ...defaultTiming };
      } else {
        localTiming = {
          sample_rate: signals.sample_rate,
          duration: signals.duration,
          rest_time: signals.rest_time,
          clock_src: signals.clock_src
        };
      }
      timingDirty = false;
    }
  );

  function updateTimingField(field: 'sample_rate' | 'duration' | 'rest_time', value: number) {
    if (!isFinite(value)) return;
    localTiming = { ...localTiming, [field]: value };
    timingDirty = true;
  }

  function updateClockSource(value: string) {
    const clock_src: ClockSource =
      value === '__internal__' ? { type: 'internal' } : { type: 'external', source: value };
    localTiming = { ...localTiming, clock_src };
    timingDirty = true;
  }

  const selectedClockValue = $derived(
    localTiming.clock_src.type === 'internal' ? '__internal__' : localTiming.clock_src.source
  );

  async function commitTiming() {
    if (!canEdit || !timingDirty || !selectedAoUid || !configSignals) return;
    const next: AOSignals = {
      sample_rate: localTiming.sample_rate,
      duration: localTiming.duration,
      rest_time: localTiming.rest_time,
      clock_src: localTiming.clock_src,
      waveforms: configSignals.waveforms
    };
    try {
      await microscope.profiles.patchAoSync(selectedAoUid, next);
      timingDirty = false;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update timing');
    }
  }

  function cancelTiming() {
    if (!configSignals) {
      localTiming = { ...defaultTiming };
    } else {
      localTiming = {
        sample_rate: configSignals.sample_rate,
        duration: configSignals.duration,
        rest_time: configSignals.rest_time,
        clock_src: configSignals.clock_src
      };
    }
    timingDirty = false;
  }

  // ──────────────────────────────── Derived timing values ────────────────────────────────

  const duration = $derived(localTiming.duration ?? 0);
  const restTime = $derived(localTiming.rest_time ?? 0);
  const sampleRate = $derived(localTiming.sample_rate ?? 0);
  const frequency = $derived(duration + restTime > 0 ? 1 / (duration + restTime) : 0);
  const samples = $derived(Math.floor(sampleRate * duration));
  const totalTime = $derived(duration + restTime);

  const formatFrequency = (hz: number): string => {
    if (hz >= 1_000_000) return `${(hz / 1_000_000).toFixed(2)} MHz`;
    if (hz >= 1_000) return `${(hz / 1_000).toFixed(2)} kHz`;
    return `${hz.toFixed(2)} Hz`;
  };

  // ──────────────────────────────── Auto-load waveform edits (debounced) ────────────────────────────────

  /**
   * Serializable fingerprint of the editing waveform. ``watch`` on this fires only
   * when the user actually mutates a field (not just on reference identity).
   */
  const editFingerprint = $derived.by<string | null>(() => {
    if (!selectedDeviceId || !editingWaveform) return null;
    return JSON.stringify({ id: selectedDeviceId, wf: $state.snapshot(editingWaveform) });
  });

  let pendingPatchTimer: ReturnType<typeof setTimeout> | null = null;

  watch(
    () => editFingerprint,
    (fp) => {
      if (!fp || !canEdit || !selectedAoUid || !configSignals || !editingWaveform || !selectedDeviceId) {
        return;
      }
      if (pendingPatchTimer) clearTimeout(pendingPatchTimer);
      // Capture snapshots for the closure
      const aoUid = selectedAoUid;
      const channelId = selectedDeviceId;
      const nextWf = cloneWaveform(editingWaveform);
      const base = configSignals;

      pendingPatchTimer = setTimeout(() => {
        pendingPatchTimer = null;
        const merged: AOSignals = {
          sample_rate: base.sample_rate,
          duration: base.duration,
          rest_time: base.rest_time,
          clock_src: base.clock_src,
          waveforms: { ...base.waveforms, [channelId]: nextWf }
        };
        void microscope.profiles.patchAoSync(aoUid, merged).catch((error: unknown) => {
          toast.error(error instanceof Error ? error.message : 'Failed to auto-load waveform');
        });
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
    if (aoRange) value = Math.max(aoRange.min, Math.min(aoRange.max, value));
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

  // ──────────────────────────────── Plot geometry ────────────────────────────────

  const plotPadding = { top: 16, right: 40, bottom: 36, left: 48 };
  let plotContainerEl = $state<HTMLDivElement>();
  let plotContainerWidth = $state(800);
  let plotContainerHeight = $state(300);

  $effect(() => {
    if (!plotContainerEl) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0) plotContainerWidth = width;
      if (height > 0) plotContainerHeight = height;
    });
    observer.observe(plotContainerEl);
    return () => observer.disconnect();
  });

  const plotData = $derived(generateTraces(displayWaveforms, duration, restTime));
  const plotResolved = $derived(resolveWaveforms(displayWaveforms));
  const plotRawRange = $derived(voltageRange(plotResolved));
  const plotYAxis = $derived(niceTicks(plotRawRange.min, plotRawRange.max));
  const plotVRange = $derived({ min: plotYAxis.min, max: plotYAxis.max });

  const plotW = $derived(plotContainerWidth - plotPadding.left - plotPadding.right);
  const plotH = $derived(plotContainerHeight - plotPadding.top - plotPadding.bottom);

  function toSvgX(t: number): number {
    if (totalTime <= 0) return plotPadding.left;
    return plotPadding.left + (t / totalTime) * plotW;
  }

  function toSvgY(v: number): number {
    const denom = plotVRange.max - plotVRange.min;
    if (denom === 0 || !isFinite(v)) return plotPadding.top + plotH * 0.5;
    const frac = (v - plotVRange.min) / denom;
    return plotPadding.top + plotH * (1 - frac);
  }

  function svgXToWindowFrac(clientX: number, rect: DOMRect): number {
    const x = clientX - rect.left;
    const t = ((x - plotPadding.left) / plotW) * totalTime;
    return duration > 0 ? t / duration : 0;
  }

  function buildPath(voltages: number[]): string {
    return plotData.time
      .map((t, i) => `${i === 0 ? 'M' : 'L'}${toSvgX(t).toFixed(1)},${toSvgY(voltages[i]).toFixed(1)}`)
      .join(' ');
  }

  function formatPlotTime(s: number): string {
    if (s >= 1) return `${s.toFixed(1)}s`;
    if (s >= 0.001) return `${(s * 1000).toFixed(1)}ms`;
    return `${(s * 1e6).toFixed(0)}\u03BCs`;
  }

  function formatVoltage(v: number): string {
    return `${v.toFixed(1)}V`;
  }

  // ──────────────────────────────── Drag handles (hidden for derived) ────────────────────────────────

  let dragging = $state<'vmin' | 'vmax' | 'wmin' | 'wmax' | null>(null);
  let frozenVRange = $state<{ min: number; max: number } | null>(null);

  function svgYToVoltageFrozen(clientY: number, rect: DOMRect): number {
    const range = frozenVRange ?? plotVRange;
    const y = clientY - rect.top;
    const frac = 1 - (y - plotPadding.top) / plotH;
    return range.min + frac * (range.max - range.min);
  }

  function onHandleDown(e: PointerEvent, handle: typeof dragging) {
    e.preventDefault();
    (e.currentTarget as SVGElement).setPointerCapture(e.pointerId);
    dragging = handle;
    if (handle === 'vmin' || handle === 'vmax') {
      frozenVRange = { min: plotVRange.min, max: plotVRange.max };
    }
  }

  function onHandleMove(e: PointerEvent) {
    if (!dragging || !editingWaveform || isDerivedWaveform(editingWaveform)) return;
    const svg = (e.currentTarget as SVGElement).closest('svg');
    if (!svg) return;
    const rect = svg.getBoundingClientRect();

    if (dragging === 'vmin' || dragging === 'vmax') {
      const voltage = svgYToVoltageFrozen(e.clientY, rect);
      if (voltageMode === 'ampoffset') {
        if (dragging === 'vmin') {
          setEditingOffset(voltage);
        } else {
          const offset = (editingWaveform.voltage.max + editingWaveform.voltage.min) / 2;
          setEditingAmplitude(Math.max(0, voltage - offset));
        }
      } else {
        if (dragging === 'vmin') {
          setEditingVoltage('min', Math.min(voltage, editingWaveform.voltage.max - 0.01));
        } else {
          setEditingVoltage('max', Math.max(voltage, editingWaveform.voltage.min + 0.01));
        }
      }
    } else {
      const frac = svgXToWindowFrac(e.clientX, rect);
      if (dragging === 'wmin') {
        editingWaveform.window.min = Math.max(0, Math.min(frac, editingWaveform.window.max - 0.01));
      } else {
        editingWaveform.window.max = Math.min(1, Math.max(frac, editingWaveform.window.min + 0.01));
      }
    }
  }

  function onHandleUp(e: PointerEvent) {
    (e.currentTarget as SVGElement).releasePointerCapture(e.pointerId);
    dragging = null;
    frozenVRange = null;
  }

  // ──────────────────────────────── Handle positions ────────────────────────────────

  const vminY = $derived.by(() => {
    if (!editingWaveform || isDerivedWaveform(editingWaveform)) return 0;
    if (voltageMode === 'ampoffset') {
      return toSvgY((editingWaveform.voltage.max + editingWaveform.voltage.min) / 2);
    }
    return toSvgY(editingWaveform.voltage.min);
  });
  const vmaxY = $derived(
    editingWaveform && !isDerivedWaveform(editingWaveform) ? toSvgY(editingWaveform.voltage.max) : 0
  );
  const wminX = $derived(
    editingWaveform && !isDerivedWaveform(editingWaveform) ? toSvgX(editingWaveform.window.min * duration) : 0
  );
  const wmaxX = $derived(
    editingWaveform && !isDerivedWaveform(editingWaveform) ? toSvgX(editingWaveform.window.max * duration) : 0
  );

  // ──────────────────────────────── Floating input positioning (anti-overlap) ────────────────────────────────

  const floatingLabelWidth = 48;
  const floatingLabelGap = 4;

  const wLabelPositions = $derived.by(() => {
    let minLeft = wminX;
    let maxLeft = wmaxX;
    const minDist = floatingLabelWidth + floatingLabelGap;
    if (maxLeft - minLeft < minDist) {
      const mid = (minLeft + maxLeft) / 2;
      minLeft = mid - minDist / 2;
      maxLeft = mid + minDist / 2;
    }
    if (minLeft < plotPadding.left) {
      const shift = plotPadding.left - minLeft;
      minLeft += shift;
      maxLeft += shift;
    }
    const rightEdge = plotPadding.left + plotW;
    if (maxLeft > rightEdge - floatingLabelWidth) {
      const shift = maxLeft - (rightEdge - floatingLabelWidth);
      maxLeft -= shift;
      minLeft -= shift;
    }
    minLeft = Math.max(plotPadding.left, minLeft);
    maxLeft = Math.min(rightEdge - floatingLabelWidth, maxLeft);
    return { minLeft, maxLeft };
  });

  const HANDLE_LINE_COLOR = '#a1a1aa';
  const handleInputColors = $derived.by(() => {
    const traceColor = selectedDeviceId ? (waveformColors[selectedDeviceId] ?? '#a1a1aa') : '#a1a1aa';
    return { vmin: traceColor, vmax: traceColor, wmin: traceColor, wmax: traceColor };
  });
</script>

{#if profile}
  <div class={cn('grid grid-rows-[auto_auto_1fr]', className)}>
    <!-- ═══ TABS (multi-AO only) ═══ -->
    {#if aoUids.length > 1}
      <div class="flex items-center gap-1 border-b px-4 py-1">
        {#each aoUids as uid (uid)}
          {@const active = uid === selectedAoUid}
          <Button variant={active ? 'outline' : 'ghost'} size="sm" onclick={() => (selectedAoUid = uid)} title={uid}>
            {sanitizeString(uid)}
          </Button>
        {/each}
      </div>
    {:else}
      <div></div>
    {/if}

    <!-- ═══ HEADER: Timing + clock source ═══ -->
    <div class="flex flex-wrap items-center justify-between gap-6 gap-y-0 border-b px-4 py-1.5">
      <div class="grid min-h-10 flex-1 grid-cols-[repeat(4,12rem)] items-center gap-3">
        <SpinBox
          value={sampleRate}
          prefix="Sample Rate"
          suffix=" Hz"
          size="xs"
          appearance="full"
          numCharacters={8}
          align="right"
          step={1}
          bigStep={1000}
          min={1000}
          disabled={!canEdit}
          onChange={(v) => updateTimingField('sample_rate', v)}
        />
        <SpinBox
          value={duration}
          prefix="Duration"
          suffix=" s"
          size="xs"
          appearance="full"
          decimals={4}
          numCharacters={8}
          align="right"
          step={0.0001}
          bigStep={0.001}
          min={0.0001}
          disabled={!canEdit}
          onChange={(v) => updateTimingField('duration', v)}
        />
        <SpinBox
          value={restTime}
          prefix="Rest Time"
          suffix=" s"
          size="xs"
          appearance="full"
          decimals={4}
          numCharacters={8}
          align="right"
          step={0.0001}
          bigStep={0.001}
          min={0}
          disabled={!canEdit}
          onChange={(v) => updateTimingField('rest_time', v)}
        />
        <Select
          prefix="Clock"
          size="xs"
          value={selectedClockValue}
          options={clockSourceOptions}
          disabled={!canEdit}
          onchange={(v) => updateClockSource(v)}
        />
      </div>
      {#if timingDirty && canEdit}
        <div class="flex min-h-10 gap-1">
          <Button variant="ghost" size="sm" onclick={cancelTiming} title="Reset timing">
            <Close width="12" height="12" />
          </Button>
          <Button variant="outline" size="sm" onclick={commitTiming} title="Apply timing">
            <Check width="12" height="12" />
          </Button>
        </div>
      {/if}
      <div class="flex min-h-8 items-center gap-4 text-xs text-fg-muted">
        <p>Freq <span class="font-mono text-nowrap text-fg">{formatFrequency(frequency)}</span></p>
        <p>Samples <span class="font-mono text-nowrap text-fg">{samples.toLocaleString()}</span></p>
      </div>
    </div>

    <!-- ═══ MAIN: Plot column (plot + chip legend) + Editor panel ═══ -->
    <div class="flex min-h-0 overflow-hidden">
      <!-- Plot column: plot (flex-1) + chip legend (auto) stacked vertically -->
      <div class="flex min-w-0 flex-1 flex-col">
        <!-- Plot area -->
        <div class="relative m-2 min-h-60 min-w-0 flex-1 overflow-hidden" bind:this={plotContainerEl}>
          {#if tabWaveformIds.length > 0 && duration > 0}
            <!-- Floating inputs (primitive waveforms only) -->
            {#if editingWaveform && selectedDeviceId && !editingIsDerived}
              {@const wf = editingWaveform}
              {#if !isDerivedWaveform(wf)}
                <input
                  type="text"
                  class="handle-input text-left"
                  style="position:absolute; top:2px; left:{wLabelPositions.minLeft}px; color:{handleInputColors.wmin};"
                  value={wf.window.min.toFixed(4)}
                  onchange={(e) => {
                    const v = parseFloat((e.target as HTMLInputElement).value);
                    if (!isNaN(v)) updateEditingWindow('min', Math.max(0, Math.min(1, v)));
                  }}
                />
                <input
                  type="text"
                  class="handle-input text-left"
                  style="position:absolute; top:2px; left:{wLabelPositions.maxLeft}px; color:{handleInputColors.wmax};"
                  value={wf.window.max.toFixed(4)}
                  onchange={(e) => {
                    const v = parseFloat((e.target as HTMLInputElement).value);
                    if (!isNaN(v)) updateEditingWindow('max', Math.max(0, Math.min(1, v)));
                  }}
                />
              {/if}
            {/if}

            <svg
              viewBox="0 0 {plotContainerWidth} {plotContainerHeight}"
              style="width: {plotContainerWidth}px; height: {plotContainerHeight}px;"
              overflow="visible"
              class="select-none"
            >
              <!-- Horizontal grid + Y-axis labels -->
              {#each plotYAxis.ticks as v (v)}
                {@const y = toSvgY(v)}
                <line
                  x1={plotPadding.left}
                  y1={y}
                  x2={plotPadding.left + plotW}
                  y2={y}
                  class="stroke-border"
                  stroke-width="1"
                />
                <text
                  x={plotPadding.left - 6}
                  {y}
                  text-anchor="end"
                  dominant-baseline="middle"
                  class="fill-fg-muted text-xs"
                >
                  {formatVoltage(v)}
                </text>
              {/each}

              <!-- Hardware voltage limit lines -->
              {#if aoRange}
                {#if aoRange.min >= plotVRange.min && aoRange.min <= plotVRange.max}
                  {@const y = toSvgY(aoRange.min)}
                  <line
                    x1={plotPadding.left}
                    y1={y}
                    x2={plotPadding.left + plotW}
                    y2={y}
                    stroke="#ef4444"
                    stroke-width="1"
                    stroke-dasharray="6 3"
                    opacity="0.4"
                  />
                  <text x={plotPadding.left + 4} y={y - 3} class="text-xs" fill="#ef4444" opacity="0.6">AO min</text>
                {/if}
                {#if aoRange.max >= plotVRange.min && aoRange.max <= plotVRange.max}
                  {@const y = toSvgY(aoRange.max)}
                  <line
                    x1={plotPadding.left}
                    y1={y}
                    x2={plotPadding.left + plotW}
                    y2={y}
                    stroke="#ef4444"
                    stroke-width="1"
                    stroke-dasharray="6 3"
                    opacity="0.4"
                  />
                  <text x={plotPadding.left + 4} y={y + 10} class="text-xs" fill="#ef4444" opacity="0.6">AO max</text>
                {/if}
              {/if}

              <!-- Rest region indicator -->
              {#if restTime > 0}
                {@const restX = toSvgX(duration)}
                <rect
                  x={restX}
                  y={plotPadding.top}
                  width={Math.max(0, plotPadding.left + plotW - restX)}
                  height={plotH}
                  class="fill-muted/15"
                />
              {/if}

              <!-- X-axis labels -->
              {#each [0, 0.25, 0.5, 0.75, 1] as frac (frac)}
                {@const t = frac * totalTime}
                {@const x = toSvgX(t)}
                <text {x} y={plotContainerHeight - 10} text-anchor="middle" class="fill-fg-muted text-xs">
                  {formatPlotTime(t)}
                </text>
              {/each}

              <!-- Handle lines (behind traces, hidden when editing a derived waveform) -->
              {#if editingWaveform && selectedDeviceId && !editingIsDerived}
                <g
                  stroke={HANDLE_LINE_COLOR}
                  stroke-width="1"
                  stroke-dasharray="4 2"
                  opacity="0.3"
                  pointer-events="none"
                >
                  <line x1={plotPadding.left} y1={vminY} x2={plotPadding.left + plotW} y2={vminY} />
                  <line x1={plotPadding.left} y1={vmaxY} x2={plotPadding.left + plotW} y2={vmaxY} />
                  <line x1={wminX} y1={plotPadding.top} x2={wminX} y2={plotPadding.top + plotH} />
                  <line x1={wmaxX} y1={plotPadding.top} x2={wmaxX} y2={plotPadding.top + plotH} />
                </g>
              {/if}

              <!-- Traces: display = streamed truth ∪ user edit -->
              <g pointer-events="none">
                {#each tabWaveformIds as deviceId (deviceId)}
                  {@const isSelected = deviceId === selectedDeviceId}
                  {@const isEditing = isSelected && !!editingWaveform}
                  {@const voltages = plotData.traces[deviceId]}
                  {#if !hiddenDevices.has(deviceId) && voltages}
                    <path
                      d={buildPath(voltages)}
                      fill="none"
                      stroke={waveformColors[deviceId] ?? '#888'}
                      stroke-width={isEditing ? 1.5 : 1}
                      stroke-linejoin="round"
                      opacity={selectedDeviceId ? (isSelected ? 0.85 : 0.4) : 0.75}
                    />
                  {/if}
                {/each}
              </g>

              <!-- Handle hit targets (primitive waveforms only) -->
              {#if editingWaveform && selectedDeviceId && !editingIsDerived}
                {@const wf = editingWaveform}
                {#if !isDerivedWaveform(wf)}
                  <g stroke="transparent" stroke-width="12">
                    <g class="cursor-ns-resize">
                      <line
                        x1={plotPadding.left}
                        y1={vminY}
                        x2={plotPadding.left + plotW}
                        y2={vminY}
                        onpointerdown={(e) => onHandleDown(e, 'vmin')}
                        onpointermove={onHandleMove}
                        onpointerup={onHandleUp}
                        role="slider"
                        tabindex="0"
                        aria-label={voltageMode === 'ampoffset' ? 'Offset' : 'Voltage minimum'}
                        aria-valuenow={wf.voltage.min}
                      />
                      <line
                        x1={plotPadding.left}
                        y1={vmaxY}
                        x2={plotPadding.left + plotW}
                        y2={vmaxY}
                        onpointerdown={(e) => onHandleDown(e, 'vmax')}
                        onpointermove={onHandleMove}
                        onpointerup={onHandleUp}
                        role="slider"
                        tabindex="0"
                        aria-label={voltageMode === 'ampoffset' ? 'Amplitude' : 'Voltage maximum'}
                        aria-valuenow={wf.voltage.max}
                      />
                    </g>
                    <g class="cursor-ew-resize">
                      <line
                        x1={wminX}
                        y1={plotPadding.top}
                        x2={wminX}
                        y2={plotPadding.top + plotH}
                        onpointerdown={(e) => onHandleDown(e, 'wmin')}
                        onpointermove={onHandleMove}
                        onpointerup={onHandleUp}
                        role="slider"
                        tabindex="0"
                        aria-label="Window minimum"
                        aria-valuenow={wf.window.min}
                      />
                      <line
                        x1={wmaxX}
                        y1={plotPadding.top}
                        x2={wmaxX}
                        y2={plotPadding.top + plotH}
                        onpointerdown={(e) => onHandleDown(e, 'wmax')}
                        onpointermove={onHandleMove}
                        onpointerup={onHandleUp}
                        role="slider"
                        tabindex="0"
                        aria-label="Window maximum"
                        aria-valuenow={wf.window.max}
                      />
                    </g>
                  </g>
                {/if}
              {/if}
            </svg>
          {:else}
            <div class="flex h-full items-center justify-center">
              <span class="text-sm text-fg-muted">No waveform data</span>
            </div>
          {/if}
        </div>

        <!-- Chip legend: horizontal below the plot, inside the plot column -->
        <div class="flex flex-wrap items-center gap-3 border-t px-4 py-2">
          {#each chipGroups as group (group.parentId)}
            {@const parentId = group.parentId}
            {@const parentSelected = parentId === selectedDeviceId}
            {@const parentHidden = hiddenDevices.has(parentId)}
            {@const parentPort = aoPorts[parentId]}
            {@const parentColor = waveformColors[parentId] ?? '#888'}
            <div class="inline-flex items-center whitespace-nowrap">
              <div
                class="inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-xs text-fg-muted transition-colors
                  {parentSelected ? 'bg-element-selected text-fg' : ''}"
              >
                <button
                  type="button"
                  class="h-2 w-2 shrink-0 rounded-full {parentSelected ? '' : 'cursor-pointer'}"
                  style={parentHidden
                    ? `border: 1px solid ${parentColor}; background: transparent;`
                    : `background-color: ${parentColor};`}
                  onclick={() => toggleDeviceVisibility(parentId)}
                  disabled={parentSelected}
                  title={parentHidden ? 'Show trace' : 'Hide trace'}
                  aria-label={parentHidden ? 'Show trace' : 'Hide trace'}
                ></button>
                <button
                  type="button"
                  class="text-left transition-colors
                    {parentSelected ? 'text-fg' : canEdit ? 'cursor-pointer hover:text-fg' : ''}"
                  onclick={() => {
                    if (canEdit) {
                      if (parentSelected) cancelEditing();
                      else selectDevice(parentId);
                    }
                  }}
                  disabled={!canEdit}
                  title={parentPort ? `${sanitizeString(parentId)} (${parentPort})` : sanitizeString(parentId)}
                >
                  <span class="mr-0.5">{sanitizeString(parentId)}</span>
                  {#if parentPort}<span class="text-fg-faint">({parentPort})</span>{/if}
                </button>
              </div>
              {#each group.children as childId (childId)}
                {@const childSelected = childId === selectedDeviceId}
                {@const childHidden = hiddenDevices.has(childId)}
                {@const childPort = aoPorts[childId]}
                {@const childColor = waveformColors[childId] ?? '#888'}
                <div class="chip-connector"></div>
                <div
                  class="chip-derived inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-xs text-fg-muted transition-colors
                    {childSelected ? 'bg-element-selected text-fg' : ''}"
                >
                  <button
                    type="button"
                    class="h-2 w-2 shrink-0 rounded-full {childSelected ? '' : 'cursor-pointer'}"
                    style={childHidden
                      ? `border: 1px solid ${childColor}; background: transparent;`
                      : `background-color: ${childColor};`}
                    onclick={() => toggleDeviceVisibility(childId)}
                    disabled={childSelected}
                    title={childHidden ? 'Show trace' : 'Hide trace'}
                    aria-label={childHidden ? 'Show trace' : 'Hide trace'}
                  ></button>
                  <button
                    type="button"
                    class="text-left transition-colors
                      {childSelected ? 'text-fg' : canEdit ? 'cursor-pointer hover:text-fg' : ''}"
                    onclick={() => {
                      if (canEdit) {
                        if (childSelected) cancelEditing();
                        else selectDevice(childId);
                      }
                    }}
                    disabled={!canEdit}
                    title={childPort ? `${sanitizeString(childId)} (${childPort})` : sanitizeString(childId)}
                  >
                    <span class="mr-0.5">{sanitizeString(childId)}</span>
                    {#if childPort}<span class="text-fg-faint">({childPort})</span>{/if}
                  </button>
                </div>
              {/each}
            </div>
          {/each}
          {#if chipGroups.length === 0}
            <span class="px-1.5 py-1 text-[10px] text-fg-muted">No waveforms</span>
          {/if}
        </div>
      </div>

      <!-- ═══ RIGHT PANEL: Waveform editor (auto-load, no Apply/Cancel) ═══ -->
      <div class="flex w-68 shrink-0 flex-col border-l">
        {#if selectedDeviceId}
          {@const port = aoPorts[selectedDeviceId]}
          <div class="flex shrink-0 items-center gap-1.5 border-b px-4 py-2 text-xs font-medium">
            <span class="h-2 w-2 rounded-full" style="background-color: {waveformColors[selectedDeviceId] ?? '#888'};"
            ></span>
            <span>{sanitizeString(selectedDeviceId)}</span>
            {#if port}<span class="text-fg-faint">({port})</span>{/if}
          </div>
        {/if}
        <div class="min-h-0 flex-1 overflow-y-auto px-4 py-2">
          {#if editingWaveform && selectedDeviceId && canEdit}
            {@const wf = editingWaveform}
            {#if isDerivedWaveform(wf)}
              <!-- Derived editor -->
              <div class="grid grid-cols-1 items-end gap-2 gap-y-3">
                <Select
                  prefix="Waveform Type"
                  size="xs"
                  value={wf.type}
                  options={waveformTypeOptions}
                  onchange={(v) => changeEditingType(v)}
                />
                <Select
                  prefix="Operation"
                  size="xs"
                  value={wf.operation}
                  options={derivedOpOptions}
                  onchange={(v) => changeDerivedOperation(v)}
                />
                <Select
                  prefix="Source"
                  size="xs"
                  value={wf.source}
                  options={derivedSourceOptions}
                  disabled={derivedSourceOptions.length === 0}
                  onchange={(v) => changeDerivedSource(v)}
                />
                {#if wf.operation === 'scale'}
                  <SpinBox
                    value={wf.factor}
                    prefix="Factor"
                    size="xs"
                    appearance="full"
                    decimals={2}
                    step={0.05}
                    numCharacters={6}
                    align="right"
                    onChange={(v) => updateEditingField('factor', v)}
                  />
                {:else if wf.operation === 'offset'}
                  <SpinBox
                    value={wf.delta}
                    prefix="Delta"
                    suffix=" V"
                    size="xs"
                    appearance="full"
                    decimals={3}
                    step={0.01}
                    numCharacters={6}
                    align="right"
                    onChange={(v) => updateEditingField('delta', v)}
                  />
                {:else if wf.operation === 'shift'}
                  <SpinBox
                    value={wf.fraction}
                    prefix="Fraction"
                    size="xs"
                    appearance="full"
                    decimals={3}
                    step={0.01}
                    min={0}
                    max={1}
                    numCharacters={6}
                    align="right"
                    onChange={(v) => updateEditingField('fraction', v)}
                  />
                {:else}
                  <div></div>
                {/if}
              </div>
            {:else}
              <!-- Primitive editor -->
              <div class="grid grid-cols-1 items-end gap-2 gap-y-3">
                <Select
                  prefix="Waveform Type"
                  size="xs"
                  value={wf.type}
                  options={waveformTypeOptions}
                  onchange={(v) => changeEditingType(v)}
                />
                <Select
                  prefix="Voltage Mode"
                  size="xs"
                  value={voltageMode}
                  options={[
                    { value: 'minmax', label: 'Min / Max' },
                    { value: 'ampoffset', label: 'Amp / Offset' }
                  ]}
                  onchange={(v) => (voltageMode = v as VoltageMode)}
                />
                {#if voltageMode === 'minmax'}
                  <SpinBox
                    value={wf.voltage.min}
                    prefix="Min V"
                    suffix=" V"
                    size="xs"
                    appearance="full"
                    decimals={3}
                    step={0.05}
                    min={aoRange?.min}
                    max={wf.voltage.max}
                    numCharacters={8}
                    align="right"
                    onChange={(v) => setEditingVoltage('min', v)}
                  />
                  <SpinBox
                    value={wf.voltage.max}
                    prefix="Max V"
                    suffix=" V"
                    size="xs"
                    appearance="full"
                    decimals={3}
                    step={0.05}
                    min={wf.voltage.min}
                    max={aoRange?.max}
                    numCharacters={8}
                    align="right"
                    onChange={(v) => setEditingVoltage('max', v)}
                  />
                {:else}
                  <SpinBox
                    value={(wf.voltage.max + wf.voltage.min) / 2}
                    prefix="Offset V"
                    suffix=" V"
                    size="xs"
                    appearance="full"
                    decimals={3}
                    step={0.05}
                    min={aoRange?.min}
                    max={aoRange?.max}
                    numCharacters={8}
                    align="right"
                    onChange={(v) => setEditingOffset(v)}
                  />
                  <SpinBox
                    value={(wf.voltage.max - wf.voltage.min) / 2}
                    prefix="Amplitude V"
                    suffix=" V"
                    size="xs"
                    appearance="full"
                    decimals={3}
                    step={0.05}
                    min={0}
                    numCharacters={8}
                    align="right"
                    onChange={(v) => setEditingAmplitude(v)}
                  />
                {/if}
                <SpinBox
                  value={wf.rest_voltage ?? 0}
                  prefix="Rest Voltage"
                  suffix=" V"
                  size="xs"
                  appearance="full"
                  decimals={2}
                  step={0.1}
                  min={wf.voltage.min}
                  max={wf.voltage.max}
                  resetValue={() => wf.voltage.min}
                  numCharacters={6}
                  align="right"
                  onChange={(v) => updateEditingField('rest_voltage', v)}
                />

                {#if wf.type === 'square' || wf.type === 'sine' || wf.type === 'triangle' || wf.type === 'sawtooth'}
                  {@const windowSpan = wf.window.max - wf.window.min}
                  {@const hasCycles = wf.cycles != null && wf.cycles > 0}
                  {@const derivedFreq =
                    hasCycles && windowSpan > 0 ? (wf.cycles ?? 0) / (windowSpan * duration) : (wf.frequency ?? 0)}
                  {#if wf.type === 'square'}
                    <SpinBox
                      value={wf.duty_cycle}
                      prefix="Duty"
                      min={0}
                      max={1}
                      step={0.05}
                      size="xs"
                      appearance="full"
                      decimals={2}
                      numCharacters={6}
                      align="right"
                      onChange={(v) => updateEditingField('duty_cycle', v)}
                    />
                  {/if}
                  <SpinBox
                    value={wf.cycles ?? 0}
                    prefix="Cycles"
                    size="xs"
                    appearance="full"
                    step={1}
                    min={0}
                    numCharacters={4}
                    align="right"
                    onChange={(v) => {
                      updateEditingField('cycles', v > 0 ? v : null);
                      if (v > 0) updateEditingField('frequency', null);
                    }}
                  />
                  <SpinBox
                    value={derivedFreq}
                    prefix="Freq"
                    suffix=" Hz"
                    size="xs"
                    appearance="full"
                    step={1}
                    min={0}
                    numCharacters={8}
                    align="right"
                    disabled={hasCycles}
                    onChange={(v) => {
                      updateEditingField('frequency', v > 0 ? v : null);
                      if (v > 0) updateEditingField('cycles', null);
                    }}
                  />
                  <SpinBox
                    value={(wf.phase ?? 0) * (180 / Math.PI)}
                    prefix="Phase"
                    suffix=" deg"
                    size="xs"
                    appearance="full"
                    step={0.1}
                    decimals={1}
                    numCharacters={6}
                    align="right"
                    onChange={(v) => updateEditingField('phase', v * (Math.PI / 180))}
                  />
                  {#if wf.type === 'triangle' || wf.type === 'sawtooth'}
                    <SpinBox
                      value={wf.symmetry ?? 1}
                      prefix="Symmetry"
                      min={0}
                      max={1}
                      step={0.05}
                      size="xs"
                      appearance="full"
                      decimals={2}
                      numCharacters={6}
                      align="right"
                      onChange={(v) => updateEditingField('symmetry', v)}
                    />
                  {/if}
                {/if}
              </div>
            {/if}
          {:else if canEdit}
            <p class="text-xs leading-ui-sm text-fg-muted">Select a waveform to edit. Changes auto-load to hardware.</p>
          {:else}
            <p class="text-xs leading-ui-sm text-warning/50">Stop acquisition to edit timing and waveforms</p>
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .handle-input {
    width: 48px;
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.6rem;
    line-height: 1;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    outline: none;
    padding: 1px 2px;
    user-select: none;
    transition: border-color 0.15s ease;
    z-index: 10;
  }

  .handle-input:hover {
    border-color: var(--color-input);
  }

  .handle-input:focus {
    border-color: var(--color-ring);
  }

  .chip-connector {
    width: 12px;
    height: 1.5px;
    background: var(--color-fg-muted);
    flex-shrink: 0;
  }
</style>
