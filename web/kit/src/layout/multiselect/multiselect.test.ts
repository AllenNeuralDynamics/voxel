import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  act,
  all,
  clickAction,
  keyAction,
  move,
  none,
  only,
  ordered,
  type Pick,
  pickState,
  range,
  same,
  solo,
  span,
  toggle
} from './multiselect.ts';

const KEYS = ['a', 'b', 'c', 'd', 'e'];

function pick(picked: string[], focus: string | null = null, anchor: string | null = focus): Pick<string> {
  return { picked: new Set(picked), focus, anchor };
}

function keys(state: Pick<string>): string[] {
  return ordered(KEYS, state.picked);
}

test('only picks 1 item, and it takes the focus and the anchor', () => {
  assert.deepEqual(only('c'), pick(['c'], 'c', 'c'));
});

test('toggle adds or removes 1 item, and moves the focus and the anchor to it', () => {
  const added = toggle(pick(['a'], 'a'), 'c');
  assert.deepEqual(keys(added), ['a', 'c']);
  assert.equal(added.focus, 'c');
  assert.equal(added.anchor, 'c');
  assert.deepEqual(keys(toggle(added, 'a')), ['c']);
  assert.deepEqual(keys(toggle(pick(['b'], 'b'), 'b')), []);
});

test('range picks the items from the anchor to the item, in both directions, and drops the others', () => {
  const down = range(pick(['b', 'e'], 'b'), KEYS, 'd');
  assert.deepEqual(keys(down), ['b', 'c', 'd']);
  assert.equal(down.focus, 'd');
  assert.equal(down.anchor, 'b');
  assert.deepEqual(keys(range(pick(['d'], 'd'), KEYS, 'a')), ['a', 'b', 'c', 'd']);
  assert.deepEqual(keys(range(pick(['c'], 'c'), KEYS, 'c')), ['c']);
});

test('range without an anchor in the list picks only the item', () => {
  assert.deepEqual(range(pick([], null), KEYS, 'c'), only('c'));
  assert.deepEqual(range(pick(['x'], 'x'), KEYS, 'c'), only('c'));
});

test('a range starts from the anchor, not from the focus', () => {
  const moved = move(pick(['b'], 'b'), KEYS, 'b', 1);
  assert.equal(moved.focus, 'c');
  assert.equal(moved.anchor, 'b');
  assert.deepEqual(keys(range(moved, KEYS, 'e')), ['b', 'c', 'd', 'e']);
});

test('solo picks only the item, and all items when it is the only pick already', () => {
  assert.deepEqual(solo(pick(['a', 'b'], 'a'), KEYS, 'c'), only('c'));
  assert.deepEqual(solo(pick(['a'], 'a'), KEYS, 'c'), only('c'));
  const back = solo(pick(['c'], 'a'), KEYS, 'c');
  assert.deepEqual(keys(back), KEYS);
  assert.equal(back.focus, 'c');
  assert.equal(back.anchor, 'c');
});

test('span gives the items from the anchor to the item the new state of the item, and keeps the others', () => {
  const on = span(pick(['e'], 'a'), KEYS, 'c');
  assert.deepEqual(keys(on), ['a', 'b', 'c', 'e']);
  assert.equal(on.focus, 'c');
  assert.equal(on.anchor, 'c');
  assert.deepEqual(keys(span(pick(KEYS, 'd'), KEYS, 'b')), ['a', 'e']);
  assert.deepEqual(keys(span(pick(['b'], 'e'), KEYS, 'c')), ['b', 'c', 'd', 'e']);
});

test('span without an anchor in the list turns only the item on or off', () => {
  assert.deepEqual(keys(span(pick(['a'], null), KEYS, 'c')), ['a', 'c']);
  assert.deepEqual(keys(span(pick(['a', 'c'], 'x'), KEYS, 'c')), ['a']);
});

test('all and none change the pick, and keep the focus and the anchor', () => {
  assert.deepEqual(all(pick(['a'], 'a'), KEYS), pick(KEYS, 'a'));
  assert.deepEqual(none(pick(KEYS, 'c', 'b')), pick([], 'c', 'b'));
});

test('move goes 1 item at a time, stops at the ends, and keeps the pick', () => {
  const start = pick(['a'], 'a');
  assert.equal(move(start, KEYS, 'a', 1).focus, 'b');
  assert.equal(move(start, KEYS, 'a', -1).focus, 'a');
  assert.equal(move(start, KEYS, 'e', 1).focus, 'e');
  assert.equal(move(start, KEYS, 'x', 1).focus, 'a');
  assert.equal(move(start, KEYS, 'x', -1).focus, 'e');
  assert.deepEqual(keys(move(start, KEYS, 'a', 1)), ['a']);
  assert.deepEqual(move(start, [], 'a', 1), start);
});

test('act applies each action to the item', () => {
  const start = pick(['a'], 'a');
  assert.deepEqual(keys(act(start, 'only', KEYS, 'c')), ['c']);
  assert.deepEqual(keys(act(start, 'solo', KEYS, 'a')), KEYS);
  assert.deepEqual(keys(act(start, 'toggle', KEYS, 'c')), ['a', 'c']);
  assert.deepEqual(keys(act(start, 'range', KEYS, 'c')), ['a', 'b', 'c']);
  assert.deepEqual(keys(act(pick(['a'], 'b'), 'span', KEYS, 'c')), ['a', 'b', 'c']);
  assert.deepEqual(keys(act(start, 'all', KEYS, 'c')), KEYS);
  assert.equal(act(start, 'next', KEYS, 'c').focus, 'd');
  assert.equal(act(start, 'previous', KEYS, 'c').focus, 'b');
});

const NO_KEYS = { shiftKey: false, metaKey: false, ctrlKey: false, altKey: false };
const CLICK = { ...NO_KEYS, detail: 1 };

test('select mode: a click picks only the item, Cmd (Ctrl) adds or removes it, and Shift picks a range', () => {
  assert.equal(clickAction(CLICK, true), 'only');
  assert.equal(clickAction({ ...CLICK, metaKey: true }, true), 'toggle');
  assert.equal(clickAction({ ...CLICK, ctrlKey: true }, false), 'toggle');
  assert.equal(clickAction({ ...CLICK, ctrlKey: true }, true), 'only');
  assert.equal(clickAction({ ...CLICK, shiftKey: true }, true), 'range');
  assert.equal(clickAction({ ...CLICK, shiftKey: true, metaKey: true }, true), 'range');
});

test('toggle mode: a click turns the item on or off, a double-click picks only it, and Shift spans', () => {
  assert.equal(clickAction(CLICK, true, 'toggle'), 'toggle');
  assert.equal(clickAction({ ...CLICK, detail: 2 }, true, 'toggle'), 'solo');
  assert.equal(clickAction({ ...CLICK, metaKey: true }, true, 'toggle'), 'toggle');
  assert.equal(clickAction({ ...CLICK, shiftKey: true }, true, 'toggle'), 'span');
  assert.equal(clickAction({ ...CLICK, shiftKey: true, detail: 2 }, true, 'toggle'), 'span');
});

test('toggle mode keys: Enter picks only the item, and Shift+Space spans', () => {
  assert.equal(keyAction({ ...NO_KEYS, key: 'Enter' }, true, 'toggle'), 'solo');
  assert.equal(keyAction({ ...NO_KEYS, key: ' ' }, true, 'toggle'), 'toggle');
  assert.equal(keyAction({ ...NO_KEYS, key: ' ', shiftKey: true }, true, 'toggle'), 'span');
  assert.equal(keyAction({ ...NO_KEYS, key: 'ArrowDown' }, true, 'toggle'), 'next');
  assert.equal(keyAction({ ...NO_KEYS, key: 'a', metaKey: true }, true, 'toggle'), 'all');
});

test('keys: arrows move, Enter picks only, Space adds or removes, Shift+Space picks a range, Cmd+A picks all', () => {
  const press = (key: string, extra: Partial<typeof NO_KEYS> = {}, mac = true) =>
    keyAction({ ...NO_KEYS, ...extra, key }, mac);
  assert.equal(press('ArrowDown'), 'next');
  assert.equal(press('ArrowUp'), 'previous');
  assert.equal(press('Enter'), 'only');
  assert.equal(press(' '), 'toggle');
  assert.equal(press(' ', { shiftKey: true }), 'range');
  assert.equal(press('a', { metaKey: true }), 'all');
  assert.equal(press('A', { metaKey: true }), 'all');
  assert.equal(press('a', { ctrlKey: true }, false), 'all');
});

test('other keys, and keys with other modifiers, do nothing here', () => {
  const press = (key: string, extra: Partial<typeof NO_KEYS> = {}, mac = true) =>
    keyAction({ ...NO_KEYS, ...extra, key }, mac);
  assert.equal(press('a'), null);
  assert.equal(press('Tab'), null);
  assert.equal(press('a', { ctrlKey: true }), null);
  assert.equal(press('a', { metaKey: true, shiftKey: true }), null);
  assert.equal(press('ArrowDown', { shiftKey: true }), null);
  assert.equal(press('ArrowDown', { metaKey: true }), null);
  assert.equal(press('Enter', { altKey: true }), null);
  assert.equal(press(' ', { metaKey: true }), null);
  assert.equal(press(' ', { ctrlKey: true }), null);
});

test('same, ordered and pickState', () => {
  assert.ok(same(new Set(['a', 'b']), new Set(['b', 'a'])));
  assert.ok(!same(new Set(['a']), new Set(['a', 'b'])));
  assert.deepEqual(ordered(KEYS, new Set(['d', 'x', 'a'])), ['a', 'd']);
  assert.equal(pickState(KEYS, new Set(KEYS)), 'all');
  assert.equal(pickState(KEYS, new Set(['b'])), 'some');
  assert.equal(pickState(KEYS, new Set(['x'])), 'none');
  assert.equal(pickState([], new Set()), 'none');
});
