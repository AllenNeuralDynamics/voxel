import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { LightPath } from '../../core/light-paths.ts';
import type { Profile } from '../../core/types.ts';
import { FlowMap, type FlowLook, type MapLayout } from './flow-map.ts';
import { LightMap } from './light-map.ts';

const path = (nodes: string[], positions: Record<string, string> = {}): LightPath => ({ nodes, positions });
const BOX = { w: 100, h: 30 };
const LOOK: FlowLook = { size: () => BOX };
const map = (paths: LightPath[]): FlowMap => new FlowMap(LightMap.edges(paths));

// Made-up rigs of different shapes.
const SINGLE = [path(['laser', 'specimen']), path(['specimen', 'camera'])];
const FAN_IN = [
  ...Array.from({ length: 8 }, (_, index) => path([`laser_${index}`, `aom_${index}`, 'combiner', 'specimen'])),
  path(['specimen', 'objective', 'camera'])
];
const ROUTER = [
  path(['laser', 'selector', 'left', 'specimen'], { selector: 'left' }),
  path(['laser', 'selector', 'right', 'specimen'], { selector: 'right' }),
  path(['specimen', 'objective', 'wheel', 'camera'])
];
const SHORT_AND_LONG = [path(['a', 'b', 'c', 'specimen']), path(['d', 'specimen']), path(['specimen', 'camera'])];
const RIGS = { SINGLE, FAN_IN, ROUTER, SHORT_AND_LONG };

/** The layer of each node, counted along the light. */
function layers(layout: MapLayout): Map<string, number> {
  const along = (node: string): number => {
    const box = layout.boxes.get(node);
    return box ? (layout.direction === 'lr' ? box.x : box.y) : 0;
  };
  const starts = [...new Set([...layout.boxes.keys()].map(along))].sort((a, b) => a - b);
  return new Map([...layout.boxes.keys()].map((node) => [node, starts.indexOf(along(node))]));
}

for (const [name, paths] of Object.entries(RIGS)) {
  for (const direction of ['lr', 'tb'] as const) {
    for (const limit of [1, 2, 3, 8]) {
      test(`${name}, ${direction}, limit ${limit}: layers stay under the limit and the light runs one way`, () => {
        const flow = map(paths);
        const at = layers(flow.layout(limit, direction, LOOK));
        const counts = new Map<number, number>();
        for (const layer of at.values()) counts.set(layer, (counts.get(layer) ?? 0) + 1);
        assert.ok(Math.max(...counts.values()) <= limit);
        for (const { from, to } of flow.edges) assert.ok((at.get(to) ?? 0) > (at.get(from) ?? 0), `${from} > ${to}`);
      });

      test(`${name}, ${direction}, limit ${limit}: boxes do not overlap, and a line passes each layer it skips`, () => {
        const layout = map(paths).layout(limit, direction, LOOK);
        const boxes = [...layout.boxes.values()];
        for (const [index, a] of boxes.entries()) {
          for (const b of boxes.slice(index + 1)) {
            assert.ok(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y);
          }
        }
        const at = layers(layout);
        for (const line of layout.lines) {
          const skipped = (at.get(line.to) ?? 0) - (at.get(line.from) ?? 0) - 1;
          assert.equal(line.points.length, 4 + 2 * skipped); // a straight piece at each end, 2 points per skipped layer
        }
      });
    }
  }
}

test('a long line runs straight through the layers it skips', () => {
  for (const paths of [SHORT_AND_LONG, FAN_IN]) {
    for (const direction of ['lr', 'tb'] as const) {
      const layout = map(paths).layout(2, direction, LOOK);
      for (const line of layout.lines.filter((one) => one.points.length > 4)) {
        const lanes = line.points.slice(2, -2).map((point) => (direction === 'lr' ? point.y : point.x));
        assert.ok(
          lanes.every((lane) => Math.abs(lane - lanes[0]) < 1e-6),
          `${line.from} > ${line.to}`
        );
      }
    }
  }
});

test('a short excitation path ends beside the specimen, not at the start', () => {
  const at = layers(map(SHORT_AND_LONG).layout(8, 'lr', LOOK));
  assert.equal(at.get('d'), at.get('c'));
});

test('8 lights into 1 combiner take more layers in a narrow area', () => {
  const flow = map(FAN_IN);
  const wide = flow.fit({ w: 2000, h: 400 }, LOOK);
  const narrow = flow.fit({ w: 300, h: 2000 }, LOOK);
  assert.equal(narrow.direction, 'tb');
  assert.ok(narrow.limit < 8);
  assert.ok(wide.width / wide.height > narrow.width / narrow.height);
});

test('the shown layout stays until another draws at least 10% larger', () => {
  const flow = map(FAN_IN);
  const shown = flow.fit({ w: 300, h: 2000 }, LOOK);
  const after = flow.fit({ w: 310, h: 2000 }, LOOK, shown);
  assert.deepEqual([after.limit, after.direction], [shown.limit, shown.direction]);
});

test("a profile lights its channel's ways that its positions allow", () => {
  const profile = { channels: { gfp: { camera: 'laser' } }, positions: { selector: 'left' } } as unknown as Profile;
  assert.deepEqual(
    LightMap.lit(ROUTER, profile).map((one) => one.nodes.join('>')),
    ['laser>selector>left>specimen', 'specimen>objective>wheel>camera']
  );
});

test('a box can have its own size, and a link meets it at its port', () => {
  const look: FlowLook = {
    size: (node) => (node === 'daq' ? { w: 100, h: 60 } : { w: 100, h: 30 }),
    port: (node, port) => (node === 'daq' ? (port === 'ao0' ? 10 : 50) : undefined)
  };
  const flow = new FlowMap([
    { from: 'daq', to: 'laser', fromPort: 'ao0', toPort: 'ttl' },
    { from: 'daq', to: 'camera', fromPort: 'ao1', toPort: 'trigger' }
  ]);
  const layout = flow.layout(8, 'lr', look);
  const daq = layout.boxes.get('daq')!;
  assert.equal(daq.h, 60);
  const [ao0, ao1] = layout.lines;
  assert.equal(ao0.points[0].y, daq.y + 10);
  assert.equal(ao1.points[0].y, daq.y + 50);
  assert.equal(ao0.points[0].x, daq.x + daq.w);
});

test('a loop is laid out one way, and its back link still runs from its real start to its real end', () => {
  const flow = new FlowMap([
    { from: 'daq', to: 'camera', fromPort: 'ao0', toPort: 'trigger_in' },
    { from: 'camera', to: 'daq', fromPort: 'trigger_out', toPort: 'pfi0' }
  ]);
  assert.deepEqual(flow.nodes, ['daq', 'camera']);
  const layout = flow.layout(8, 'lr', LOOK);
  const daq = layout.boxes.get('daq')!;
  const camera = layout.boxes.get('camera')!;
  assert.ok(camera.x > daq.x);
  const back = layout.lines.find((line) => line.from === 'camera')!;
  assert.equal(back.to, 'daq');
  assert.ok(back.points[0].x > back.points.at(-1)!.x); // drawn right to left, from the camera back to the daq
});

test('a link leaves and meets its boxes flat', () => {
  const layout = map(FAN_IN).layout(2, 'lr', LOOK);
  for (const line of layout.lines) {
    const [a, b] = line.points;
    const [y, z] = line.points.slice(-2);
    assert.equal(a.y, b.y);
    assert.equal(y.y, z.y);
  }
});

// A sender with 4 pins, each to its own receiver: the sender sits alone in its layer.
const FAN_OUT = new FlowMap(
  ['a', 'b', 'c', 'd'].map((pin) => ({ from: 'daq', to: `dev_${pin}`, fromPort: pin, toPort: 'in' }))
);
const PINS: FlowLook = {
  size: (node, _direction, extra) => ({ w: 100, h: (node === 'daq' ? 4 * 10 : 20) + extra }),
  port: (node, port, _direction, extra) =>
    node === 'daq' ? (['a', 'b', 'c', 'd'].indexOf(port) + 0.5) * (10 + extra / 4) : undefined,
  stretch: (node) => node === 'daq'
};

test('a box that may stretch grows to the breadth its layer beside it has, and the map keeps its size', () => {
  const tight = FAN_OUT.layout(Infinity, 'lr', { ...PINS, stretch: undefined });
  const grown = FAN_OUT.layout(Infinity, 'lr', PINS);
  assert.equal(grown.height, tight.height);
  assert.equal(grown.boxes.get('daq')!.h, grown.height);
});

test('a map too tall for its area spreads its layers, up to the largest gap', () => {
  const plain = FAN_OUT.layout(Infinity, 'lr', PINS);
  const wide = FAN_OUT.layout(Infinity, 'lr', PINS, { area: { w: 2000, h: plain.height }, gap: { max: 200 } });
  assert.equal(wide.height, plain.height);
  assert.ok(wide.width > plain.width);
  assert.ok(wide.width <= 2 * 100 + 200 + 1e-9);
});

test('while the map fits its area, the boxes of a layer move apart, up to the largest spacing', () => {
  const plain = FAN_OUT.layout(Infinity, 'lr', PINS);
  const tops = (layout: MapLayout): number[] => ['a', 'b', 'c', 'd'].map((pin) => layout.boxes.get(`dev_${pin}`)!.y);
  const spread = FAN_OUT.layout(Infinity, 'lr', PINS, { area: { w: 1000, h: 300 }, spacing: { max: 1000 } });
  assert.ok(Math.abs(spread.height - 300) < 1e-6);
  // Boxes keep their size; only the space between them grows.
  for (const pin of ['a', 'b', 'c', 'd']) assert.equal(spread.boxes.get(`dev_${pin}`)!.h, 20);
  // A box that may stretch grows to its layer's new breadth, to line its ports up.
  assert.ok(Math.abs(spread.boxes.get('daq')!.h - 300) < 1e-6);
  // The gap stops at its largest size.
  const capped = FAN_OUT.layout(Infinity, 'lr', PINS, { area: { w: 1000, h: 300 }, spacing: { max: 30 } });
  const at = tops(capped);
  for (let index = 1; index < at.length; index++) assert.ok(Math.abs(at[index] - at[index - 1] - (20 + 30)) < 1e-6);
  // A map too big for its area at real size keeps its spacing.
  const small = FAN_OUT.layout(Infinity, 'lr', PINS, { area: { w: 50, h: 300 }, spacing: { max: 1000 } });
  assert.deepEqual(tops(small), tops(plain));
});

test('fill never changes a map whose boxes may not stretch, across the flow', () => {
  const plain = map(FAN_IN).layout(8, 'lr', LOOK);
  const filled = map(FAN_IN).layout(8, 'lr', LOOK, { area: { w: plain.width, h: 10_000 } });
  assert.equal(filled.height, plain.height);
});

test('arrow keys step to the nearest item that way on screen; Home and End to the ends', () => {
  const places = new Map([
    ['a', { x: 0, y: 0 }],
    ['b', { x: 0, y: 10 }],
    ['c', { x: 100, y: 0 }],
    ['d', { x: 30, y: 40 }]
  ]);
  assert.equal(FlowMap.step('ArrowDown', 'a', places), 'b');
  assert.equal(FlowMap.step('ArrowRight', 'a', places), 'c');
  assert.equal(FlowMap.step('ArrowUp', 'a', places), undefined);
  assert.equal(FlowMap.step('ArrowLeft', 'c', places), 'a');
  assert.equal(FlowMap.step('Home', 'c', places), 'a');
  assert.equal(FlowMap.step('End', 'a', places), 'd');
  assert.equal(FlowMap.step('Enter', 'a', places), undefined);
});
