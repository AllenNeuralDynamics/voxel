# @voxel/station

The new station app, for the new core (`vxl.instrument`, `vxl.station`). It is empty so far. Its design is the Lab
prototype, linked from `prototypes/TODO.md` (Web layer). The old app is `web/legacy`.

From the repository root:

```bash
vp -C web install
vp -C web/station dev
vp -C web/station run check
vp -C web/station build
```

The build is a single-page app in `web/station/build/`. Where the gateway serves it from is not decided yet.
