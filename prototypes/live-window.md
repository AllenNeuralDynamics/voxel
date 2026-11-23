# Live profile: docked or undocked

Agreed on 2026-11-22. Not built. Try-out: "Live as a Page" v16
(https://claude.ai/artifact/AHxHq7U22TCKTckknDu5aF). Browser tests ran in Chrome 157 and Safari 27.3 on macOS.

## The design

The live profile (the image, Profile, Preview and the light settings of the open instrument) is in exactly 1 place:

| State | Where |
| --- | --- |
| Docked | The side pane of the workspace window |
| Undocked | A separate window, the Live window |

The workspace is the main window: the rail, the pages, the app bar and, while docked, the side pane.

### Logo menu

| Item | Where | Shown |
| --- | --- | --- |
| Show live profile | Workspace | While undocked |
| Show workspace | Live window | Always |
| Settings | Both | Always |
| Live profile `[Docked │ Undocked]` | Both | Always, text segments, no tooltips. Hidden on phones (not agreed yet) |
| Mode `[sun │ moon │ monitor]` | Both | Always |

"Show" brings the other window to the front. It never changes docked or undocked. Words chosen so they are true in a
tab, a browser window and a desktop app window: no "tab", "window" or "pop".

### Live window

- Route `/stations/<id>/live`. No rail. Path `Dev / <open instrument> / Live`. Title `Live · <instrument> · Voxel`.
- The bar: path, then `[Layout │ Swap]`, Profile, Preview.
- Links in it open in the workspace.
- Closing it (the browser's own close) docks the live profile.
- Only the workspace opens it. A Live page with no parent window (typed, bookmarked) goes to the workspace with
  `location.replace`, docked.

### App bar (option B)

- An instrument that is not open shows `[Open]` at the bar's end. If another instrument is open, Open asks first:
  "Close Z Step and open X Sweep Oblique?"
- The amber "Z Step is open" note goes.
- While docked and viewing another instrument, the pane heading is `Z Step / Live`; "Z Step" is a link that shows it.
  Viewing the open instrument, it is `Live`.

## Browser facts (tested)

| Need | Method | Result, Chrome and Safari |
| --- | --- | --- |
| Undock | `window.open('', 'voxel-live', 'popup')`; set the URL only when it returns `about:blank` | A real window (`toolbar.visible` false) |
| Show live profile | The same call, then `focus()` | Finds the open window, no reload, comes to the front |
| Show workspace | `window.opener.focus()` | **Fails**: a popup cannot raise its opener |
| Show workspace | `<a target="voxel-workspace" href="<workspace address>#workspace">` | Comes to the front, no reload |
| Repeat Show workspace | The same fixed `#workspace` link | Chrome: 1 Back step in total. Safari: none |
| A link to another page | `<a target="voxel-workspace" href="/other/page">` | Comes to the front, but reloads the whole app |
| Reload the Live window | Cmd+R | `window.opener` survives |
| Dock from the workspace | `BroadcastChannel` message, the Live window calls `window.close()` | Closes |
| Know Live is open | `BroadcastChannel` "open" and "closed" (`pagehide`) | Works, also across unrelated tabs |
| Find a typed tab by name | `window.open('', 'voxel-live')` | **Fails** both ways: unrelated tabs do not see each other's names, and the call makes a blank tab |

Not tested: Firefox, phones. The `#workspace` link did not fire `hashchange` in the workspace, so the workspace must not
rely on it.

So a page link in the Live window is the fixed `#workspace` link (to raise the workspace) plus a `BroadcastChannel`
message with the path (the workspace then moves there with SvelteKit's `goto`, no reload).

## Code layout (proposed)

2 layers: a domain-free pair of window classes that know nothing of Voxel, and 1 Voxel class over them.

### Domain-free: `web/station/src/lib/core/utils/linked-windows.svelte.ts`

1 file, 1 message protocol over 1 `BroadcastChannel`, 2 classes, 1 per side.

**The parent's side, `ChildWindow`:**

```ts
class ChildWindow {
  constructor(options: { name: string; channel: string; url: () => string });
  readonly isOpen: boolean;        // $state: from "here" and "gone" messages; asks once on start
  show(): void;                    // find by name or load url(); popup; focus. Never reloads an open window
  close(): void;                   // asks the child to close itself
  onNavigate(handler: (path: string) => void): () => void; // the child asked to go to a path
  dispose(): void;
}
```

It also answers "address" questions with its own address, so the child can build the raise link.

**The child's side, `ParentWindow`:**

```ts
class ParentWindow {
  constructor(options: { name: string; parent: string; channel: string });
  readonly connected: boolean;     // the parent window is set (window.opener)
  link(path?: string): { href: string; target: string; onclick: () => void }; // props for an <a>
  dispose(): void;
}
```

- It names its window, says "here" on start and "gone" on `pagehide`, and closes itself on "close".
- `link()` gives the fixed `#workspace` link to the parent's last known address. With `path`, its `onclick` also
  sends "navigate". Spread it on an `<a>`, for "Show workspace" and for every link in the Live window.

The fragment (`workspace`) is an option, not a Voxel word, in the generic code. Messages: `here`, `gone`, `close`, `address`, `navigate`.

### Voxel: `web/station/src/lib/shell/live-dock.svelte.ts`

```ts
class LiveDock {
  constructor(stationId: () => string);
  readonly docked: boolean;   // !child.isOpen
  undock(): void;             // child.show()
  dock(): void;               // child.close()
  show(): void;               // child.show(), only while undocked
  dispose(): void;
}
```

It owns a `ChildWindow` named `voxel-live` (the workspace names itself `voxel-workspace`), the URL
`/stations/<id>/live`, and passes "navigate" to `goto`. `LiveDock.workspace()` makes the Live window's
`ParentWindow`, so the window names and the channel are in 1 place. The workspace layout makes the `LiveDock`; no
context yet, since nothing else reads it.

A `navigate` waits 150 ms in the parent before it moves, so the `#workspace` change of the same click lands first.
Moving first would turn that change into a load of the old page. Not tested in the browsers yet.

### Svelte parts

- **`LiveProfile.svelte`**, the live profile's content: 1 component, because 2 places show it: the side pane and the Live route. This is
  the 1 new component the design needs.
- **Routes**: the Live window must not get the workspace frame (rail, page pane). So the station's routes split:
  - `routes/stations/[stationId]/+layout.svelte`: what both windows need (station, selection, connection).
  - `routes/stations/[stationId]/(workspace)/+layout.svelte`: today's frame, with the side pane hidden while
    undocked. `instruments/` and `settings/` move under it. The `(workspace)` group does not change any URL.
  - `routes/stations/[stationId]/live/+page.svelte`: the Live window. It uses `ParentWindow` and does the
    no-parent redirect.
- **`LogoMenu.svelte`**: the logo menu, now a component because both windows show it. Its items take an action:
  `onclick`, or `href` and `target` (the Live window spreads `ParentWindow.link()` on them).
- **AppBar**: option B (always Open, no amber note).

## Open

- Phones: hide the Docked row.
- Firefox: not tested.
