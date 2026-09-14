# Original stage feature references

Archived browser-owned snapshot and inpainting implementations, retained for
reference when building their backend-first replacements. These are not active
Konva components.

- `features/Snapshots.svelte.txt`: snapshot display, grouping, and selection.
- `features/Inpaint.svelte.txt`: mosaic recording, compositing, and erasing.
- `draw.ts.txt`: the original drawing, camera, and geometry helpers.
- `scene.svelte.ts.txt`: layer registration, hit testing, and scene state.

The original relative directory structure is preserved. The `.txt` suffix keeps
these files out of compilation and type checking; their imports are historical
references, not runnable dependencies. Imports outside the old stage directory
(such as application models and preview utilities) have not been archived here.

The original Stage viewer has been removed. These files preserve the two feature
components and their drawing and scene dependencies. The still-active stage
controls, gizmo, and its 3D camera math now live under `lib/stage/`.
