# Task metadata

Agreed on 2026-11-18 in the Lab (`Voxel Station Prototype`). Backend changes 1, 2, 3, 4, 5 and 8 are built (2026-11-20);
the rest of the backend and all of `web/` are not. The Lab draws
the Run page's Task card and the History page's Tasks tab this way.

## The design

- **A task's metadata follows its instrument's metadata class** (`InstrumentState.metadata_cls`), a subclass of
  `vxl.metadata.ExperimentMetadata`. Each task keeps its own values in `plan[].metadata`, so 2 regions of 1 specimen can
  differ (for example a brain mounted again has new directions).
- **Groups are nested models.** A class says how its fields group in its structure, not in a marker:

  ```python
  class Chamber(BaseModel):
      medium: str = "other"
      refractive_index: float = 1.33


  class AnatomicalDirections(BaseModel):
      x: AnatomicalDirectionX = "Anterior_to_posterior"
      y: AnatomicalDirectionY = "Inferior_to_superior"
      z: AnatomicalDirectionZ = "Left_to_right"


  class ExaspimMetadata(ExperimentMetadata):
      subject_id: str = key(default="")
      experimenters: list[str] = Field(default_factory=list)
      chamber: Chamber = Field(default_factory=Chamber)
      anatomical_directions: AnatomicalDirections = Field(default_factory=AnatomicalDirections)
  ```

  Why: the JSON schema already describes a nested model as an object with a title, so any UI can draw "an object field
  is a group with that title" with no rule of its own. The saved data reads better too:
  `anatomical_directions: {x, y, z}`. Rejected: a `group="Chamber"` marker on flat fields (a custom rule where the
  schema already has nesting), and a flat list (a long card; titles such as "Chamber medium" repeat the group).
- **A class may mark 1 key field**, with `key()` next to `annotation()`. Tasks with the same key value are about the
  same thing. exaSPIM marks `subject_id`; a bead calibration class might mark `slide_id`, or nothing.
  - With a key: a task's full name is its key value, then its own name, joined by a slash with no spaces
    (`M-2816/cortex`, the task inside its key, as in storage paths); the Run page groups tasks
    by it. This is only how a screen shows a task: its `id` is unique across the plan in every case.
  - Without a key: names show alone.
- **Provenance and annotations.** Fields are provenance by default and lock after the first acquisition that uses the
  task. Fields made with `annotation()` (the base class's `notes`) stay editable afterwards.
- **Required fields** are marked in the class with `required()`, so the run check is generic ("cortex: Subject id is
  empty."). A pydantic field with no default is not used for this: it would refuse a new task before it is filled in.

## How a UI draws it

From the class's JSON schema only, for any class:

| Schema | Drawn as |
|---|---|
| a text, number or choice field | a row: its title at the left, its value at the right |
| a list of text | a row; the values joined with commas, or a comma-separated box in Edit |
| an object (a nested model) | a group: the model's title at the left, its fields as rows under it |
| long text (`notes`) | a row across the full width; up to 2 lines in the read view |
| the key field | first, and in the task's heading |

- Choices show their values with spaces for underscores ("Anterior to posterior"). Shorter labels would have to come
  from the class.
- **Read view first, Edit on request.** The card shows plain text; Edit shows the boxes and menus. Both views use the
  same rows at the same heights, so Edit moves nothing. After a run, Edit opens only the annotation fields. A new task
  opens in Edit.
- The same read view shows a task on the Run page and in History (Tasks tab), where it is the metadata frozen with the
  acquisition's `instrument_state`.
- A value that is not in the schema (left from another form) shows at the end under its own name, so nothing is
  hidden.

## Backend changes needed

| # | Change | Where | State |
|---|---|---|---|
| 1 | `Chamber` and `AnatomicalDirections` models; `ExaspimMetadata` uses them | `drivers/src/vxl_drivers/metadata.py` | built |
| 2 | `key()`, beside `annotation()`: marks the key field in the JSON schema (for example `isKey`); at most 1 per class, checked when the class is made | `src/vxl/metadata.py` | built |
| 3 | `ExperimentMetadata.key_field()`, as `annotation_fields()` | `src/vxl/metadata.py` | built |
| 4 | `required()`, next to `key()`: marks a field that must be filled in before a run (`isRequired` in the schema). The field keeps a default, so a new task is accepted with it empty. The key field is always required. `ExperimentMetadata.empty_required(values)` gives each empty one, also inside groups; `start_acquisition` refuses with 1 `task.metadata.required` problem at each field ("cortex: Subject id is empty.") | `src/vxl/metadata.py`, `Instrument._metadata_problems`, SPIM's `start_acquisition` | built |
| 5 | `_update_task_metadata` merges nested values (a deep merge); today it merges top-level keys only, so editing `chamber.medium` would drop `chamber.refractive_index` | `src/vxl/instrument/base.py` | built |
| 6 | Lock provenance fields of a task once an acquisition used it; annotation fields stay editable | `src/vxl/instrument/base.py` | not built: needs a design |
| 7 | Dropped (2026-11-20): a task `id` stays unique across the plan, as the plan's key and the routes need. The key value with the id (`M-2816/cortex`) is only how a screen shows a task | — | dropped |
| 8 | The form's JSON schema in the view, so it goes out as a feed topic (picked 2026-11-20). Today the view holds only the class path `metadata_cls`, so a window cannot draw the form. A new view field, `metadata_schema` (the topic `instrument.metadata_schema`), and 1 line in `_view_sources`; it changes with `set_metadata_class`, in the same message as the refitted plan | `src/vxl/instrument/base.py` | built |

Checked on 2026-11-20 with a nested try-out form: storing a nested value and its JSON schema (`$defs`, `$ref`) already
work. Change 5 is a real loss today: an edit of `chamber: {medium: water}` set a stored `refractive_index` of 1.52 back
to the default 1.33, with no error. Rejected for change 8: a `GET /metadata:schema` route, where a window could hold
new values with the old schema until it asks again.

The legacy app keeps the flat form as its own class, `vxl._legacy.metadata.ExaspimMetadata` (2026-11-20), so the
nested class shares nothing with legacy.

### To decide

- **Change 6:** where the fact "an acquisition used this task" lives.

## Frontend changes needed

In the new app, `web/station`. The legacy app is frozen; its `MetadataEditor.svelte`
(`web/legacy/src/lib/features/run/`) and `JsonSchemaProperty` (`web/legacy/src/lib/core/model/types.ts`) show what
exists today.

| # | Change | Where |
|---|---|---|
| 1 | Nested objects: resolve `$ref`/`$defs` and draw a group per object | the metadata editor |
| 2 | The key mark: the key field first, in the task's heading, and the Run page grouped by it | the metadata editor, the Run page |
| 3 | `JsonSchemaProperty` gains `$ref`, `properties` and the key mark | the schema types |
| 4 | The read view and Edit, with no layout shift; after a run only annotations open | the metadata editor |

## Open questions

- A key value that contains `/` (the subject field takes any text) would read as 2 steps in `M-2816/cortex`. Either
  refuse `/` in key values, as task names already allow only letters, digits, `_` and `-`, or show such names another
  way.
- Display labels for choices: keep the values with spaces, or let a class give short labels.
- A task heading when the class has no key field: its name alone (current pick).
- Whether History may edit annotations of a past acquisition, and where that edit is stored: the acquisition record is
  frozen at Start.
