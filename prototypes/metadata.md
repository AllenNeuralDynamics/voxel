# Task metadata

Agreed on 2026-11-18 in the Lab (`Voxel Station Prototype`); nothing is built in `src/` or `web/` yet. The Lab draws
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
    by it; a name only has to be unique among tasks with the same key value.
  - Without a key: names show alone and must be unique across the plan.
- **Provenance and annotations.** Fields are provenance by default and lock after the first acquisition that uses the
  task. Fields made with `annotation()` (the base class's `notes`) stay editable afterwards.
- **Required fields** come from the class, so the run check is generic ("cortex: Subject ID is empty").

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

| # | Change | Where |
|---|---|---|
| 1 | `Chamber` and `AnatomicalDirections` models; `ExaspimMetadata` uses them | `drivers/src/vxl_drivers/metadata.py` |
| 2 | `key()`, beside `annotation()`: marks the key field in the JSON schema (for example `isKey`); at most 1 per class, checked when the class is made | `src/vxl/metadata.py` |
| 3 | `ExperimentMetadata.key_field()`, as `annotation_fields()` | `src/vxl/metadata.py` |
| 4 | Required fields in the class drive the run check | `src/vxl/metadata.py`, the task checks |
| 5 | `_update_task_metadata` merges nested values (a deep merge); today it merges top-level keys only, so editing `chamber.medium` would drop `chamber.refractive_index` | `src/vxl/instrument/base.py` |
| 6 | Lock provenance fields of a task once an acquisition used it; annotation fields stay editable | `src/vxl/instrument/base.py` |
| 7 | Names unique per key value when the class has a key, else across the plan | the plan checks |

## Frontend changes needed

| # | Change | Where |
|---|---|---|
| 1 | Nested objects: resolve `$ref`/`$defs` and draw a group per object | `web/legacy/src/lib/features/run/MetadataEditor.svelte` |
| 2 | The key mark: the key field first, in the task's heading, and the Run page grouped by it | `MetadataEditor.svelte`, the Run page |
| 3 | `JsonSchemaProperty` gains `$ref`, `properties` and the key mark | `web/legacy/src/lib/core/model/types.ts` |
| 4 | The read view and Edit, with no layout shift; after a run only annotations open | `MetadataEditor.svelte` |

## Open questions

- A key value that contains `/` (the subject field takes any text) would read as 2 steps in `M-2816/cortex`. Either
  refuse `/` in key values, as task names already allow only letters, digits, `_` and `-`, or show such names another
  way.
- Display labels for choices: keep the values with spaces, or let a class give short labels.
- A task heading when the class has no key field: its name alone (current pick).
- Whether History may edit annotations of a past acquisition, and where that edit is stored: the acquisition record is
  frozen at Start.
