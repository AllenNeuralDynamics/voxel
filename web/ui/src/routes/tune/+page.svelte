<script lang="ts">
  import { Collapsible } from 'bits-ui';
  import { Pane, PaneGroup } from 'paneforge';
  import { watch } from 'runed';
  import { SvelteSet } from 'svelte/reactivity';
  import { toast } from 'svelte-sonner';

  import { resolveDeviceColor, waveformPortColor } from '$lib/colors.svelte';
  import { Check, ChevronDown, Close } from '$lib/icons';
  import { Button, Select } from '$lib/kit';
  import PaneDivider from '$lib/kit/PaneDivider.svelte';
  import type { SelectOption } from '$lib/kit/Select.svelte';
  import type { AOSignals, ClockSource, DerivedWaveform, Waveform } from '$lib/model';
  import { getVoxelApp } from '$lib/model';
  import { SpinBox } from '$lib/prop/numeric';
  import { createPaneSize, sanitizeString, toastError } from '$lib/utils';

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
    clock_src: ClockSource;
  }

  const defaultTiming: Timing = {
    sample_rate: 100000,
    duration: 0.01,
    rest_time: 0,
    clock_src: { type: 'internal' }
  };

  // ──────────────────────────────── Pure helpers ────────────────────────────────

  function formatFrequency(hz: number): string {
    if (hz >= 1_000_000) return `${(hz / 1_000_000).toFixed(2)} MHz`;
    if (hz >= 1_000) return `${(hz / 1_000).toFixed(2)} kHz`;
    return `${hz.toFixed(2)} Hz`;
  }

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

  // ──────────────────────────────── AO tab state ────────────────────────────────

  /** All AO devices referenced by this profile's sync block. */
  const aoUids = $derived<string[]>(profile ? Object.keys(profile.sync) : []);

  /** Options for the AO device <Select>. Maps each uid to a display label. */
  const aoOptions = $derived<SelectOption[]>(aoUids.map((uid) => ({ value: uid, label: sanitizeString(uid) })));

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

  // Reset timing-dirty flag when profile changes. Re-anchoring of ``selectedDeviceId``
  // is handled by the ``tabWaveformIds`` watch further down.
  watch(
    () => instrument?.activeProfileId,
    () => {
      timingDirty = false;
    },
    { lazy: true }
  );

  // ──────────────────────────────── Source of truth (streamed loaded + config) ────────────────────────────────

  const loadedSignals = $derived.by<AOSignals | null>(() => {
    if (!selectedAoUid) return null;
    return instrument?.analogOuts.get(selectedAoUid)?.loaded ?? null;
  });

  const configSignals = $derived.by<AOSignals | null>(() => {
    if (!profile || !selectedAoUid) return null;
    return profile.sync[selectedAoUid] ?? null;
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

  const aoRange = $derived.by<{ min: number; max: number } | null>(() => {
    if (!selectedAoUid) return null;
    return instrument?.analogOuts.get(selectedAoUid)?.voltageRange ?? null;
  });

  const aoPorts = $derived.by<Record<string, string>>(() => {
    if (!selectedAoUid) return {};
    const dev = instrument?.hal.devices[selectedAoUid];
    const ports = dev?.init?.ports as Record<string, string> | undefined;
    return ports ?? {};
  });

  const aoTriggers = $derived.by<Record<string, string>>(() => {
    if (!selectedAoUid) return {};
    const dev = instrument?.hal.devices[selectedAoUid];
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

  /** Device ids that have a waveform entry in the current AO tab's signals.
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

  // Window edit lens: absolute seconds within [0, duration] (default), or raw fractions [0,1] the API expects.
  type WindowMode = 'percent' | 'seconds';
  let windowMode = $state<WindowMode>('seconds');

  /** Radio-button selection: clicking the currently-selected row is a no-op.
   *  ``selectedDeviceId`` is always anchored to a valid row when the tab has any
   *  waveforms — see the ``tabWaveformIds`` watch below. There is no explicit
   *  "deselect" path. */
  function selectDevice(deviceId: string) {
    if (deviceId === selectedDeviceId) return;
    const source = baseWaveforms[deviceId];
    if (!source) return;
    selectedDeviceId = deviceId;
    editingWaveform = cloneWaveform(source);
  }

  // Auto-select: whenever the tab's waveform list changes (new profile, new AO tab,
  // or ``baseWaveforms`` shift), re-anchor ``selectedDeviceId`` to a valid row —
  // defaulting to the first — or clear it only when there's nothing to select.
  // Subsumes the old ``selectedAoUid`` / ``cancelEditing`` watch.
  watch(
    () => tabWaveformIds,
    (ids) => {
      if (ids.length === 0) {
        selectedDeviceId = null;
        editingWaveform = null;
        return;
      }
      if (!selectedDeviceId || !ids.includes(selectedDeviceId)) {
        selectDevice(ids[0]);
      }
    }
  );

  /** Merge the user's in-flight edit over the base waveforms for plotting + resolution. */
  const displayWaveforms = $derived.by<Record<string, Waveform>>(() => {
    if (!selectedDeviceId || !editingWaveform) return baseWaveforms;
    return { ...baseWaveforms, [selectedDeviceId]: editingWaveform };
  });

  // ──────────────────────────────── Timing (explicit Apply) ────────────────────────────────

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
      await instrument?.updateAoSignals(selectedAoUid, next);
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

  let pendingPatchTimer: ReturnType<typeof setTimeout> | null = null;

  watch(
    () => editFingerprint,
    (fp) => {
      if (!fp || !canEdit || !selectedAoUid || !configSignals || !editingWaveform || !selectedDeviceId) {
        return;
      }
      if (pendingPatchTimer) clearTimeout(pendingPatchTimer);
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
        toastError(instrument?.updateAoSignals(aoUid, merged));
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

  // ──────────────────────────────── Plot context (bundled chrome for WaveformPanel) ────────────────────────────────

  /** Device-wide chrome shared by every ``WaveformPanel`` on the page. Panels are
   *  self-sizing (internal ``ResizeObserver``), so layout dimensions aren't here. */
  const plotContext = $derived<import('./WaveformPanel.svelte').PlotContext>({
    duration,
    restTime,
    aoRange,
    syncKey: 'tune'
  });

  // ──────────────────────────────── Outer pane layout ────────────────────────────────

  let paneGroupEl = $state<HTMLElement | null>(null);
  const sidebarSize = createPaneSize(() => paneGroupEl, {
    min: 260,
    max: 320,
    fallback: {
      min: 30,
      max: 40,
      default: 30
    }
  });
  const mainPanelSize = createPaneSize(() => paneGroupEl, {
    min: 350,
    fallback: {
      min: 55,
      default: 70
    }
  });
</script>

{#if profile}
  <div class="flex h-full flex-col">
    <!-- Top bar: AO selector + derived readouts. Timing moved to sidebar footer. -->
    <div class="flex shrink-0 flex-wrap items-center gap-6 border-b px-4 py-1.5">
      <Select
        prefix="AO"
        size="xs"
        class="w-48"
        value={selectedAoUid ?? ''}
        options={aoOptions}
        disabled={aoOptions.length === 0}
        onchange={(v) => (selectedAoUid = v)}
      />
      <div class="ml-auto flex min-h-8 items-center gap-4 text-xs text-fg-muted">
        <p>Freq <span class="font-mono text-nowrap text-fg">{formatFrequency(frequency)}</span></p>
        <p>Samples <span class="font-mono text-nowrap text-fg">{samples.toLocaleString()}</span></p>
      </div>
    </div>
    <PaneGroup bind:ref={paneGroupEl} direction="horizontal" autoSaveId="tune" class="min-h-0 flex-1">
      <Pane class="pb-4" {...mainPanelSize}>
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
                <div class="flex items-center gap-1 px-1 text-xs text-fg-muted">
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
            <div class="flex h-full items-center justify-center text-sm text-fg-muted">No waveform data</div>
          {/if}
        </div>
      </Pane>

      <PaneDivider direction="vertical" />

      <Pane {...sidebarSize}>
        <div class="flex h-full flex-col border-l">
          {#if selectedDeviceId && editingWaveform}
            {@const port = aoPorts[selectedDeviceId]}
            {@const wf = editingWaveform}
            <!-- Device header: id + port -->
            <div class="flex shrink-0 items-center gap-1.5 border-b px-4 py-2 text-xs font-medium">
              <span>{sanitizeString(selectedDeviceId)}</span>
              {#if port}<span class="text-fg-faint">({port})</span>{/if}
            </div>

            <!-- Editor body: scrolls if content exceeds pane height -->
            <div class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
              {#if !canEdit}
                <p class="mb-3 text-xs text-warning/80">Acquiring — controls are read-only.</p>
              {/if}

              {#if isDerivedWaveform(wf)}
                <!-- Derived-waveform editor -->
                <div class="grid grid-cols-1 items-end gap-2 gap-y-3">
                  <Select
                    prefix="Waveform Type"
                    size="xs"
                    value={wf.type}
                    options={waveformTypeOptions}
                    disabled={!canEdit}
                    onchange={(v) => changeEditingType(v)}
                  />
                  <Select
                    prefix="Operation"
                    size="xs"
                    value={wf.operation}
                    options={derivedOpOptions}
                    disabled={!canEdit}
                    onchange={(v) => changeDerivedOperation(v)}
                  />
                  <Select
                    prefix="Source"
                    size="xs"
                    value={wf.source}
                    options={derivedSourceOptions}
                    disabled={!canEdit || derivedSourceOptions.length === 0}
                    onchange={(v) => changeDerivedSource(v)}
                  />
                  {#if wf.operation === 'scale'}
                    <SpinBox
                      model={{
                        value: wf.factor,
                        onChange: (v) => updateEditingField('factor', v),
                        step: 0.05
                      }}
                      prefix="Factor"
                      size="xs"
                      decimals={2}
                      numCharacters={6}
                      align="right"
                      disabled={!canEdit}
                    />
                  {:else if wf.operation === 'offset'}
                    <SpinBox
                      model={{
                        value: wf.delta,
                        onChange: (v) => updateEditingField('delta', v),
                        step: 0.01
                      }}
                      prefix="Delta"
                      suffix=" V"
                      size="xs"
                      decimals={3}
                      numCharacters={6}
                      align="right"
                      disabled={!canEdit}
                    />
                  {:else if wf.operation === 'shift'}
                    <SpinBox
                      model={{
                        value: wf.fraction,
                        onChange: (v) => updateEditingField('fraction', v),
                        min: 0,
                        max: 1,
                        step: 0.01
                      }}
                      prefix="Fraction"
                      size="xs"
                      decimals={3}
                      numCharacters={6}
                      align="right"
                      disabled={!canEdit}
                    />
                  {/if}
                </div>
              {:else}
                <!-- Primitive-waveform editor -->
                <div class="flex flex-col gap-5">
                  <Select
                    prefix="Waveform Type"
                    size="xs"
                    value={wf.type}
                    options={waveformTypeOptions}
                    disabled={!canEdit}
                    onchange={(v) => changeEditingType(v)}
                  />

                  <!-- Voltage -->
                  <section class="flex flex-col gap-2">
                    <h3 class="text-[10px] font-semibold tracking-wider text-fg-muted uppercase">Voltage</h3>
                    <Select
                      prefix="Mode"
                      size="xs"
                      value={voltageMode}
                      options={[
                        { value: 'minmax', label: 'Min / Max' },
                        { value: 'ampoffset', label: 'Amp / Offset' }
                      ]}
                      disabled={!canEdit}
                      onchange={(v) => (voltageMode = v as VoltageMode)}
                    />
                    {#if voltageMode === 'minmax'}
                      <div class="flex flex-wrap gap-2">
                        <SpinBox
                          model={{
                            value: wf.voltage.min,
                            onChange: (v) => setEditingVoltage('min', v),
                            min: aoRange?.min,
                            max: wf.voltage.max,
                            step: 0.05
                          }}
                          prefix="Min"
                          suffix=" V"
                          size="xs"
                          decimals={3}
                          numCharacters={6}
                          align="right"
                          disabled={!canEdit}
                          class="min-w-32 flex-1"
                        />
                        <SpinBox
                          model={{
                            value: wf.voltage.max,
                            onChange: (v) => setEditingVoltage('max', v),
                            min: wf.voltage.min,
                            max: aoRange?.max,
                            step: 0.05
                          }}
                          prefix="Max"
                          suffix=" V"
                          size="xs"
                          decimals={3}
                          numCharacters={6}
                          align="right"
                          disabled={!canEdit}
                          class="min-w-32 flex-1"
                        />
                      </div>
                    {:else}
                      <div class="grid grid-cols-2 gap-2">
                        <SpinBox
                          model={{
                            value: (wf.voltage.max + wf.voltage.min) / 2,
                            onChange: (v) => setEditingOffset(v),
                            min: aoRange?.min,
                            max: aoRange?.max,
                            step: 0.05
                          }}
                          prefix="Offset"
                          suffix=" V"
                          size="xs"
                          decimals={3}
                          numCharacters={6}
                          align="right"
                          disabled={!canEdit}
                        />
                        <SpinBox
                          model={{
                            value: (wf.voltage.max - wf.voltage.min) / 2,
                            onChange: (v) => setEditingAmplitude(v),
                            min: 0,
                            step: 0.05
                          }}
                          prefix="Amp"
                          suffix=" V"
                          size="xs"
                          decimals={3}
                          numCharacters={6}
                          align="right"
                          disabled={!canEdit}
                        />
                      </div>
                    {/if}
                    <SpinBox
                      model={{
                        value: wf.rest_voltage ?? 0,
                        onChange: (v) => updateEditingField('rest_voltage', v),
                        min: wf.voltage.min,
                        max: wf.voltage.max,
                        step: 0.1,
                        home: () => wf.voltage.min
                      }}
                      prefix="Rest Voltage"
                      suffix=" V"
                      size="xs"
                      decimals={2}
                      numCharacters={6}
                      align="right"
                      disabled={!canEdit}
                    />
                  </section>

                  <!-- Timing: the active window, as fractions of the duration or absolute seconds -->
                  <section class="flex flex-col gap-2">
                    <h3 class="text-[10px] font-semibold tracking-wider text-fg-muted uppercase">Timing</h3>
                    <Select
                      prefix="Mode"
                      size="xs"
                      value={windowMode}
                      options={[
                        { value: 'percent', label: 'Percent' },
                        { value: 'seconds', label: 'Seconds' }
                      ]}
                      disabled={!canEdit}
                      onchange={(v) => (windowMode = v as WindowMode)}
                    />
                    {#if windowMode === 'percent'}
                      <div class="flex flex-wrap gap-2">
                        <SpinBox
                          model={{
                            value: wf.window.min,
                            onChange: (v) => updateEditingWindow('min', v),
                            min: 0,
                            max: wf.window.max,
                            step: 0.01,
                            bigStep: 0.05
                          }}
                          prefix="Start"
                          size="xs"
                          decimals={3}
                          numCharacters={5}
                          align="right"
                          disabled={!canEdit}
                          class="min-w-32 flex-1"
                        />
                        <SpinBox
                          model={{
                            value: wf.window.max,
                            onChange: (v) => updateEditingWindow('max', v),
                            min: wf.window.min,
                            max: 1,
                            step: 0.01,
                            bigStep: 0.05
                          }}
                          prefix="End"
                          size="xs"
                          decimals={3}
                          numCharacters={5}
                          align="right"
                          disabled={!canEdit}
                          class="min-w-32 flex-1"
                        />
                      </div>
                    {:else}
                      <div class="flex flex-wrap gap-2">
                        <SpinBox
                          model={{
                            value: wf.window.min * duration,
                            onChange: (v) => updateEditingWindow('min', duration > 0 ? v / duration : 0),
                            min: 0,
                            max: wf.window.max * duration,
                            step: 0.0001,
                            bigStep: 0.001
                          }}
                          prefix="Start"
                          suffix=" s"
                          size="xs"
                          decimals={4}
                          numCharacters={6}
                          align="right"
                          disabled={!canEdit || duration <= 0}
                          class="min-w-32 flex-1"
                        />
                        <SpinBox
                          model={{
                            value: wf.window.max * duration,
                            onChange: (v) => updateEditingWindow('max', duration > 0 ? v / duration : 0),
                            min: wf.window.min * duration,
                            max: duration,
                            step: 0.0001,
                            bigStep: 0.001
                          }}
                          prefix="End"
                          suffix=" s"
                          size="xs"
                          decimals={4}
                          numCharacters={6}
                          align="right"
                          disabled={!canEdit || duration <= 0}
                          class="min-w-32 flex-1"
                        />
                      </div>
                    {/if}
                  </section>

                  <!-- Shape -->
                  {#if wf.type === 'square' || wf.type === 'sine' || wf.type === 'triangle' || wf.type === 'sawtooth'}
                    {@const windowSpan = wf.window.max - wf.window.min}
                    {@const hasCycles = wf.cycles != null && wf.cycles > 0}
                    {@const derivedFreq =
                      hasCycles && windowSpan > 0 ? (wf.cycles ?? 0) / (windowSpan * duration) : (wf.frequency ?? 0)}
                    <section class="flex flex-col gap-2">
                      <h3 class="text-[10px] font-semibold tracking-wider text-fg-muted uppercase">Shape</h3>
                      {#if wf.type === 'square'}
                        <SpinBox
                          model={{
                            value: wf.duty_cycle,
                            onChange: (v) => updateEditingField('duty_cycle', v),
                            min: 0,
                            max: 1,
                            step: 0.05
                          }}
                          prefix="Duty"
                          size="xs"
                          decimals={2}
                          numCharacters={6}
                          align="right"
                          disabled={!canEdit}
                        />
                      {/if}
                      <SpinBox
                        model={{
                          value: wf.cycles ?? 0,
                          onChange: (v) => {
                            updateEditingField('cycles', v > 0 ? v : null);
                            if (v > 0) updateEditingField('frequency', null);
                          },
                          min: 0,
                          step: 1
                        }}
                        prefix="Cycles"
                        size="xs"
                        numCharacters={4}
                        align="right"
                        disabled={!canEdit}
                      />
                      <SpinBox
                        model={{
                          value: derivedFreq,
                          onChange: (v) => {
                            updateEditingField('frequency', v > 0 ? v : null);
                            if (v > 0) updateEditingField('cycles', null);
                          },
                          min: 0,
                          step: 1
                        }}
                        prefix="Freq"
                        suffix=" Hz"
                        size="xs"
                        numCharacters={8}
                        align="right"
                        disabled={!canEdit || hasCycles}
                      />
                      <SpinBox
                        model={{
                          value: (wf.phase ?? 0) * (180 / Math.PI),
                          onChange: (v) => updateEditingField('phase', v * (Math.PI / 180)),
                          step: 0.1
                        }}
                        prefix="Phase"
                        suffix=" deg"
                        size="xs"
                        decimals={1}
                        numCharacters={6}
                        align="right"
                        disabled={!canEdit}
                      />
                      {#if wf.type === 'triangle' || wf.type === 'sawtooth'}
                        <SpinBox
                          model={{
                            value: wf.symmetry ?? 1,
                            onChange: (v) => updateEditingField('symmetry', v),
                            min: 0,
                            max: 1,
                            step: 0.05
                          }}
                          prefix="Symmetry"
                          size="xs"
                          decimals={2}
                          numCharacters={6}
                          align="right"
                          disabled={!canEdit}
                        />
                      {/if}
                    </section>
                  {/if}
                </div>
              {/if}
            </div>

            <!-- Timing footer: device-scoped params, always pinned to bottom of sidebar -->
            <div class="shrink-0 border-t px-4 pt-2 pb-3">
              <div class="mb-2 flex items-center justify-between">
                <h3 class="text-[10px] font-semibold tracking-wider text-fg-muted uppercase">Clock</h3>
                <div class="flex gap-1">
                  <Button
                    variant={timingDirty ? 'danger' : 'ghost'}
                    size="icon-xs"
                    disabled={!timingDirty || !canEdit}
                    onclick={cancelTiming}
                    title="Reset clock"
                  >
                    <Close width="14" height="14" />
                  </Button>
                  <Button
                    variant={timingDirty ? 'success' : 'ghost'}
                    size="icon-xs"
                    disabled={!timingDirty || !canEdit}
                    onclick={commitTiming}
                    title="Apply clock"
                  >
                    <Check width="14" height="14" />
                  </Button>
                </div>
              </div>
              <div class="grid grid-cols-1 items-end gap-2 gap-y-3">
                <Select
                  prefix="Clock"
                  size="xs"
                  value={selectedClockValue}
                  options={clockSourceOptions}
                  disabled={!canEdit}
                  onchange={(v) => updateClockSource(v)}
                />
                <SpinBox
                  model={{
                    value: sampleRate,
                    onChange: (v) => updateTimingField('sample_rate', v),
                    min: 1000,
                    step: 1,
                    bigStep: 1000
                  }}
                  prefix="Sample Rate"
                  suffix=" Hz"
                  size="xs"
                  numCharacters={8}
                  align="right"
                  disabled={!canEdit}
                />
                <SpinBox
                  model={{
                    value: duration,
                    onChange: (v) => updateTimingField('duration', v),
                    min: 0.0001,
                    step: 0.0001,
                    bigStep: 0.001
                  }}
                  prefix="Duration"
                  suffix=" s"
                  size="xs"
                  decimals={4}
                  numCharacters={8}
                  align="right"
                  disabled={!canEdit}
                />
                <SpinBox
                  model={{
                    value: restTime,
                    onChange: (v) => updateTimingField('rest_time', v),
                    min: 0,
                    step: 0.0001,
                    bigStep: 0.001
                  }}
                  prefix="Rest Time"
                  suffix=" s"
                  size="xs"
                  decimals={4}
                  numCharacters={8}
                  align="right"
                  disabled={!canEdit}
                />
              </div>
            </div>
          {:else}
            <div class="flex h-full items-center justify-center text-sm text-fg-muted">No waveforms available</div>
          {/if}
        </div>
      </Pane>
    </PaneGroup>
  </div>
{:else}
  <div class="flex h-full items-center justify-center text-sm text-fg-muted">Select a profile to view waveforms</div>
{/if}
