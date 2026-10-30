# Themes

A theme sets the colors of the app. Each theme defines 50 tokens, once for light mode and once for dark mode.
`base.css` adds 5 data tokens that all themes share, and `roles.css` derives 8 more tokens and defines the frames and notes.

## Rules

1. The theme sets every color. Shared CSS can point a token at another token, but it never makes a new color.
2. Components use tokens as they are. They never make see-through copies, such as `bg-danger/10`.
3. Each job has 1 token, and each token has 1 job. A token does 2 jobs only when its value meets the contrast rules of
   both.
4. Each meaning has 1 colored family. Families never share a color, and they all have the same shape.
5. A locked control fades as a whole, to 50%. That is a state, not a color, so it has no token.

In the tables below, "every layer" means the 5 solid layers: `--canvas`, `--pane`, `--shell`, `--raised` and
`--floating`.

## Files

| File                                        | Contents                                                                                      |
| ------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `base.css`                                  | The Default theme, under `:root` (light) and `.dark`, and the 5 shared data tokens            |
| `<id>.light.css`, `<id>.dark.css`           | A theme, under `[data-theme='<id>']` and `[data-theme='<id>'].dark`                           |
| `roles.css`                                 | The derived tokens and the looks                                                              |
| `index.css`                                 | Imports the files above                                                                       |
| `manager.svelte.ts`                         | The theme registry, and the mode, density and mark color settings                             |
| `AppearanceMenu.svelte`                     | The quick appearance settings in a menu, on the dashboard bar and the connection splash       |
| `ModeSwitch.svelte`                         | The light, dark and auto switch inside a menu, in the appearance menu and the station menu    |
| `ThemePicker.svelte`, `MarkSettings.svelte` | The full appearance settings, on the station Settings page and in the UI Lab                  |
| `colors.ts`                                 | Color helpers, such as the color of a wavelength and a color that reads in light or dark mode |
| `index.ts`                                  | The public exports of this folder                                                             |

## Layers

| Token               | Use                                                                       |
| ------------------- | ------------------------------------------------------------------------- |
| `--canvas`          | The middle area: the preview and drawings                                 |
| `--pane`            | The left and right panes, where content goes, and dialogs                 |
| `--shell`           | The app shell: the top bar, the rail, toolbars and footers                |
| `--raised`          | A block lifted inside a pane or on the canvas                             |
| `--floating`        | Menus, popovers, tooltips and select lists                                |
| `--tint`            | See-through: a quiet group that sets content apart, on any layer          |
| `--tint-hover`      | See-through: a clickable area under the pointer, on any layer             |
| `--overlay`         | See-through: a panel over the preview image                               |
| `--backdrop`        | See-through: the dim behind a dialog                                      |
| `--raised-shadow`   | Edge of a raised block: a shadow in light mode, a faint line in dark mode |
| `--floating-shadow` | Edge of floating parts                                                    |

- The first 5 are solid. 2 of them can have the same color.
- `--shell` sits between `--pane` and `--raised`, or has the same color as `--pane`, so bars sit on top of content.
- In dark mode, `--raised` is 1.25:1 above `--pane`. In light mode, `--raised` is the lightest layer, and its shadow
  lifts it.
- A page header is part of its page, so it takes the page color.
- Layers that touch, such as the shell and a pane, need different colors or a line between them.
- A raised block stands out from the pane and the canvas.
- A menu stands out from a card. In light mode, the shadows do this. In dark mode, `--floating` is lighter than
  `--raised`.
- `--fg` reads at 4.5:1 on `--tint` and `--tint-hover`.

## Frames

A frame sets the corners, the edge and the background of 1 box. A part with a frame adds none of its own, and a frame
adds no padding or layout. The frames are utilities in `roles.css`, sorted by where the box sits against its layer.

| Frame               | Sits           | Corners | Background                                     | Edge                                                         | Used by                                    |
| ------------------- | -------------- | ------- | ---------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------ |
| `frame-raised`      | Above          | Large   | `--raised`                                     | `--raised-shadow`                                            | Cards                                      |
| `frame-raised-link` | Above          | Large   | `--raised`, and `--floating` under the pointer | `--raised-shadow`, and `--floating-shadow` under the pointer | Cards that are links or buttons            |
| `frame-floating`    | Above          | Medium  | `--floating`                                   | `--floating-shadow`                                          | Menus, popovers, tooltips and select lists |
| `frame-dialog`      | Above          | Large   | `--pane`                                       | `--floating-shadow`                                          | Dialogs and side sheets                    |
| `frame-tinted`      | Level          | Medium  | `--tint`                                       | None                                                         | Quiet groups                               |
| `frame-bordered`    | Level          | Large   | None                                           | 1px `--line-muted` ring                                      | Groups, also inside a raised box           |
| `frame-sunken`      | Below          | Small   | `--canvas`                                     | 1px `--line-faint` ring                                      | Logs, lists and code                       |
| `frame-overlay`     | Over the image | Small   | `--overlay`, blurred                           | 1px `--line-muted` ring and a large shadow                   | Panels over the preview                    |
| `frame-placeholder` | Level          | Large   | None                                           | 1px dashed `--line-muted` outline, inside the box            | Empty places                               |

- A dialog holds content like a pane, so it takes the pane color. The backdrop lifts it.
- A side sheet sits on the screen edge, so it has no corners.
- Edges are rings in the shadows or outlines, not borders, so text inside a part lines up with text outside it.
- A raised box inside a raised box looks heavy. Use `frame-bordered` for the inner box.

### Docked

A box drops the corners on each edge it touches, such as a card docked on the bottom edge of a pane. Add 1 modifier
per edge, next to the frame: `frame-docked-top`, `frame-docked-right`, `frame-docked-bottom` and `frame-docked-left`.
With `Section`, pass the modifier in `class`.

## Notes

A note is the family tint with a muted line in the family color. Its text and icons use the family `-fg` color,
which the content sets. There is no neutral note: use `frame-tinted`.

| Note           | Background       | Edge                       |
| -------------- | ---------------- | -------------------------- |
| `note-accent`  | `--accent-tint`  | 1px `--accent-muted` ring  |
| `note-success` | `--success-tint` | 1px `--success-muted` ring |
| `note-warning` | `--warning-tint` | 1px `--warning-muted` ring |
| `note-danger`  | `--danger-tint`  | 1px `--danger-muted` ring  |

## Adding a frame or a note

- Add one only when 2 or more places need it and no frame fits.
- It sets corners, edge and background only.
- Its name says what it does to the box, not where it is used.
- Add it to the tables above and to the Surfaces page of the UI Lab, in `src/routes/(dashboard)/ui-lab/surfaces/`.

## Control fills

Each fill is the text color, see-through, so it looks the same on every layer. From weakest to strongest:

| Token                | Use                                      |
| -------------------- | ---------------------------------------- |
| `--element-bg`       | Control box fill                         |
| `--element-hover`    | Control under the pointer                |
| `--element-selected` | Current item in a list, menu or RadioBar |
| `--element-active`   | Control while pressed                    |
| `--track`            | Empty part of a slider or meter          |

- Each fill is stronger than the one before it, on every layer.
- `--fg` reads at 4.5:1 on each fill, on every layer.

## Text

| Token        | Use                    | Contrast                                                |
| ------------ | ---------------------- | ------------------------------------------------------- |
| `--fg`       | Text and icons         | 4.5:1 on every layer                                    |
| `--fg-muted` | Labels                 | 4.5:1 on every layer, on `--element-bg` and on `--tint` |
| `--fg-faint` | Placeholders and hints | 3:1 on every layer and on `--element-bg`                |

`--element-bg` and `--tint` on a menu are not checked. They are rare there, and in dark mode the rule would make muted
text almost as light as `--fg`.

## Lines

| Token                  | Use                                | Contrast on every layer | Default        |
| ---------------------- | ---------------------------------- | ----------------------- | -------------- |
| `--line`               | Strong lines and edges             | 2:1 or more             |                |
| `--line-muted`         | Lines and dividers                 | 1.6:1 or more           |                |
| `--line-faint`         | Quiet dividers                     | 1.3:1 or more           |                |
| `--line-selected`      | Line around a selected item        | 3:1 or more             |                |
| `--control-line`       | Control box line                   |                         | `--line-muted` |
| `--control-line-hover` | Control box line under the pointer |                         | `--line`       |

The first 4 are see-through, so each line is the same step on every layer. The control lines are derived in
`roles.css`, and a theme can set them to change the default.

## Colored families

| Family    | Meaning                                                                                    |
| --------- | ------------------------------------------------------------------------------------------ |
| `accent`  | On or checked, a camera in preview, value marks such as a slider knob, and the main button |
| `danger`  | Errors, actions you cannot undo, and a laser that is on                                    |
| `warning` | Problems that do not block                                                                 |
| `success` | Done or OK, and a running acquisition                                                      |

Each family sets 6 tokens, where `X` is the family name:

| Token       | Use                                                                                                       | Contrast                                                       |
| ----------- | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `--X`       | Solid fills: the main button, checked boxes and badges                                                    |                                                                |
| `--on-X`    | Text and icons on `--X`                                                                                   | 4.5:1 on `--X` and `--X-hover`                                 |
| `--X-hover` | `--X` under the pointer, or pressed                                                                       |                                                                |
| `--X-muted` | Quieter fills: sliders, progress, levels and the note line. `--accent-muted` is also behind selected text | Visible against `--track`. `--fg` at 4.5:1 on `--accent-muted` |
| `--X-tint`  | Behind text: notes, badges and highlights                                                                 | `--fg` at 4.5:1 on it                                          |
| `--X-fg`    | Text, icons, dots and lines in the family color                                                           | 4.5:1 on every layer and on `--X-tint`                         |

- A note is `--X-tint` with a `--X-muted` line, and `--X-fg` text and icons.
- `--on-warning` is a dark color in every theme. A yellow light enough to look like a warning is too light for white
  text.
- A small warning dot uses `--warning`, not `--warning-fg`. In light mode, `--warning-fg` must be dark to read as
  text, and a small dot of it looks gray. The Issues tab dot uses `--danger` and `--warning` as a pair.
- There is no info family. An info note uses neutral text and an icon.
- A part that moves, such as a stage axis or a filter wheel, pulses. It has no color.

## Data and marks

| Token                                             | Use                                                                                        | Contrast             | Default                                            |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------ | -------------------- | -------------------------------------------------- |
| `--series-1` to `--series-4`                      | Groups on the stage map, plot lines and JSON values                                        | 4.5:1 on every layer |                                                    |
| `--stage-mark`                                    | The stage position: the marker, the field-of-view boxes, the grid and the off-screen arrow |                      |                                                    |
| `--axis-x`, `--axis-y`, `--axis-z`                | The X, Y and Z axes                                                                        |                      | `--danger-fg`, `--success-fg`, `--accent-fg`       |
| `--axis-x-tint`, `--axis-y-tint`, `--axis-z-tint` | Behind an axis label that is on                                                            |                      | `--danger-tint`, `--success-tint`, `--accent-tint` |

- `base.css` sets the series colors and `--stage-mark` for all themes. A theme can set them to change them.
- `--stage-mark` is the same in light and dark mode. Routing does not use it.
- The axes default to danger, success and accent, so X, Y and Z are red, green and blue, as in 3D tools.
- A user can pick the stage mark and the axis colors in the appearance settings. A pick wins over the theme, and the app
  makes a picked axis color lighter or darker for each mode.
- Data colors can share a hue with a family, because they show only in plots, maps and the axes.
- Plot lines in the sync view do not use tokens. Lasers and cameras take their hue from the wavelength. Filters, the
  stage and waveforms use a fixed set for each mode.
- Other marks use the neutral tokens. A selection and the minimap viewport box are `--fg`. Routing lines and plan
  tasks are `--fg-muted`. Grid tiles use the line, tint and control fill tokens.
- Text and marks on the stage map or on a camera image use the `halo` utility from `roles.css`: a soft edge in
  `--canvas`, so they read on any image.

## Other

| Token                     | Use                                                                     | Contrast           |
| ------------------------- | ----------------------------------------------------------------------- | ------------------ |
| `--focus`                 | Focus ring. On round parts and accent parts, it sits outside with a gap | 3:1 on every layer |
| `--scrollbar-thumb`       | Scrollbar handle                                                        |                    |
| `--scrollbar-thumb-hover` | Scrollbar handle under the pointer                                      |                    |

## Using tokens

Tailwind classes such as `bg-raised` and `text-fg-muted` read the tokens through the `--color-*` mapping in
[`src/routes/layout.css`](../../../routes/layout.css). A new token needs a line there.

## Adding a theme

1. Create `<id>.light.css` and `<id>.dark.css`. Set all 50 tokens in each, under `[data-theme='<id>']` and
   `[data-theme='<id>'].dark`.
2. Import both files in `index.css`.
3. Add an entry with `id`, `name` and `swatches` to the registry in `manager.svelte.ts`.
4. Check the contrast rules above in both modes.

## Modes and density

| Setting     | Values                             | Effect                                                                                                                                                                |
| ----------- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mode        | Light, Dark, Auto                  | Toggles the `.dark` class on the root element. Auto follows the system.                                                                                               |
| Density     | 12, 13, 14 or 15 px. Default 14    | Sets the root font size to 75%, 81.25%, 87.5% or 93.75%. Sizes in rem scale with it. Saved as the size. Each size has a label: Compact, Cozy, Comfortable or Spacious |
| Mark colors | Stage mark, X axis, Y axis, Z axis | Overrides the theme for these tokens                                                                                                                                  |
