# vxl-cli

Unified command-line interface for Voxel.

Install the core checker and node command with `vxl-cli`, or include an
application extra:

```bash
uv add "vxl-cli[web]"
uv add "vxl-cli[qt]"
uv add "vxl-cli[all]"
```

Initialize a control station before starting the web or Qt application:

```bash
vxl station init --name my-microscope
```

This creates `~/.voxel/station.yaml` and refuses to replace an existing station. The `vxl node` command does not
require a station and can use `~/.voxel/system.yaml`, `VOXEL_*` environment variables, or defaults.
