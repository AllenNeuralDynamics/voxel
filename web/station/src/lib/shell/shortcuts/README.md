# Shortcuts

The keyboard and mouse shortcuts of the web UI. Voxel drives lasers, cameras and stages, so starting hardware must be
deliberate, and stopping it must be easy.

## Rules

1. **The risk of an action decides its keys.**

   | Kind of action        | Examples                                            | Keys                                                                |
   | --------------------- | --------------------------------------------------- | ------------------------------------------------------------------- |
   | View only             | Show the grid, switch a tab, open the shortcut list | 1 key, or hold a modifier                                           |
   | Settings you can undo | Exposure, laser level                               | Only in the focused control: arrows, Alt+scroll. ⌘Z undoes          |
   | Start hardware        | Preview, a stage move                               | ⌘ (Ctrl) plus a key. Never 1 key alone                              |
   | Stop hardware         | Stop preview, halt the stage                        | 1 easy chord that always works, with no confirm                     |
   | Long or final         | Start a run, close the instrument, delete           | No shortcut, or a 2-step chord that opens a confirm, like ⌘K then Q |

2. **Each modifier has 1 meaning.** ⌘ (Ctrl on Windows and Linux) is for commands, such as undo, preview and close.
   Shift is for more, such as big steps and ranges. Alt is for a closer look and fine control, such as the stage grid,
   value readouts, Alt+scroll and drawing a region.
3. **Keys that you hold act only where the pointer is.** Alt shows the stage grid only over the stage map, and the
   laser readout only over the laser plot. So Alt+scroll on a number box does not change the stage.
4. **No app shortcut fires while you type.** In a text field, ⌘Z undoes the typing, not the instrument.
5. **Every shortcut is visible,** in the tooltip of its button, for example "Preview (⌘ P)", and in the list that "?"
   opens.
6. **1 file lists all shortcuts:** [`registry.ts`](registry.ts). Each entry has the keys, a label, the area where it works and its
   kind. The handlers, the tooltips and the list read from it, and a test checks that no 2 shortcuts take the same keys
   in the same area.
   - `useShortcut(id, run)` registers a chord or a sequence. It never fires while you type, and a start, stop or final
     chord fires only once while you hold its keys.
   - A gesture, such as Alt+drag, has an entry too, but its component handles it.
   - `shortcutText(id)` gives the keys as people see them, such as "⌘ Z" on a Mac and "Ctrl+Z" on Windows.

## Decisions

- The number controls step with Alt+scroll, not ⌘+scroll. Ctrl+scroll zooms the page, a trackpad pinch also sends
  Ctrl, and Shift+scroll scrolls sideways. A plain scroll never changes a value, so scrolling the page cannot change a
  laser level.
- Space does not start preview. 1 key would turn on the lasers too easily.
- The stop chord is ⌘. (Ctrl+.), because ⌘. already means "stop" on a Mac.
