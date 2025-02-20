from typing import Any

import psutil
from ruamel.yaml import YAML


def clean_yaml_file(file_path: str) -> None:
    # remove extra newlines at the end of each section
    with open(file_path) as f:
        lines = f.readlines()
    with open(file_path, "w") as f:
        f.writelines([line for line in lines if line.strip() != ""])


def update_yaml_content(file_path: str, new_content: dict[str, Any]) -> None:
    try:
        yaml = YAML(typ="safe")
        yaml.default_flow_style = False
        yaml.indent(mapping=2, sequence=4, offset=2)

        # Read existing content
        try:
            with open(file_path) as file:
                data = yaml.load(file) or {}
        except FileNotFoundError:
            data = {}

        # Update content
        data.update(new_content)

        # Write updated content
        with open(file_path, "w") as file:
            for key, value in data.items():
                yaml.dump({key: value}, file)
                file.write("\n")
    except Exception as e:
        raise ValueError(f"Error updating YAML content: {e}")


def get_available_disk_space_mb(path: str) -> int:
    """Return the available disk space in mega bytes."""
    return psutil.disk_usage(path).free // (1024**2)
