import assert from 'node:assert/strict';
import { test } from 'node:test';

import { conflicts, type Shortcut, SHORTCUTS } from './registry.ts';

test('no 2 shortcuts take the same keys in the same area', () => {
  assert.deepEqual(conflicts(SHORTCUTS), []);
});

test('Mod is ⌘ on a Mac and Ctrl elsewhere, so a clash can be on 1 platform only', () => {
  const shortcuts: Record<string, Shortcut> = {
    save: { keys: 'Mod+S', label: 'Save', area: 'app', kind: 'edit' },
    windowsSave: { keys: 'Control+S', label: 'Save', area: 'stage', kind: 'edit' },
    macSave: { keys: 'Meta+S', label: 'Save', area: 'laser plot', kind: 'edit', platforms: ['mac'] }
  };
  assert.deepEqual(conflicts(shortcuts), ['save and windowsSave on windows', 'save and macSave on mac']);
});

test('shortcuts in 2 different areas do not clash, but an app shortcut clashes with all areas', () => {
  const shortcuts: Record<string, Shortcut> = {
    stageCancel: { keys: 'Escape', label: 'Cancel', area: 'stage', kind: 'view' },
    plotCancel: { keys: 'Escape', label: 'Cancel', area: 'laser plot', kind: 'view' }
  };
  assert.deepEqual(conflicts(shortcuts), []);
  const withApp = { ...shortcuts, close: { keys: 'Escape', label: 'Close', area: 'app', kind: 'final' } } as const;
  assert.deepEqual(conflicts(withApp), ['stageCancel and close on mac', 'plotCancel and close on mac']);
});

test('sequences and gestures are compared too', () => {
  const shortcuts: Record<string, Shortcut> = {
    close: { sequence: ['Mod+K', 'Q'], label: 'Close', area: 'app', kind: 'final' },
    quit: { sequence: ['Mod+K', 'Q'], label: 'Quit', area: 'app', kind: 'final' },
    grid: { gesture: 'hold', modifier: 'Alt', label: 'Grid', area: 'stage', kind: 'view' },
    region: { gesture: 'drag', modifier: 'Alt', label: 'Region', area: 'stage', kind: 'view' }
  };
  assert.deepEqual(conflicts(shortcuts), ['close and quit on mac']);
});
