"""Static instrument checking and terminal/JSON reporting."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from vxl.instrument.bench import InstrumentBench, InstrumentInspection
from vxl.instrument.errors import Violation
from vxl.system import System, load_voxel_env


@dataclass(frozen=True)
class TargetCheck:
    path: Path
    inspection: InstrumentInspection | None = None
    input_violations: tuple[Violation, ...] = ()

    @property
    def ok(self) -> bool:
        return self.inspection is not None and self.inspection.ok

    @property
    def violations(self) -> tuple[Violation, ...]:
        return self.inspection.violations if self.inspection is not None else self.input_violations


def _input_error(path: Path, message: str, code: str) -> TargetCheck:
    return TargetCheck(
        path,
        input_violations=(Violation(code=code, msg=message),),
    )


def _check_path(path: Path) -> TargetCheck:
    if path.is_file():
        return TargetCheck(path, InstrumentBench.check_config(path))
    if path.is_dir() and (path.suffix == ".voxel" or (path / "config.yaml").exists()):
        return TargetCheck(path, InstrumentBench.check(path))
    return _input_error(path, f"Unsupported check target: {path}", "target.unsupported")


def _children(path: Path) -> list[Path]:
    configs = path.glob("*.voxel.yaml")
    instruments = (child for child in path.glob("*.voxel") if child.is_dir())
    return sorted([*configs, *instruments])


def collect_checks(paths: list[Path]) -> list[TargetCheck]:
    """Expand requested files/directories and check each concrete target."""
    if not paths:
        root = System().dir / "instruments"
        return [_check_path(path) for path in _children(root)] if root.is_dir() else []

    targets: list[TargetCheck] = []
    for path in paths:
        if not path.exists():
            targets.append(_input_error(path, f"Check target does not exist: {path}", "target.not_found"))
        elif path.is_dir() and path.suffix != ".voxel" and not (path / "config.yaml").exists():
            children = _children(path)
            if children:
                targets.extend(_check_path(child) for child in children)
            else:
                targets.append(_input_error(path, f"No instrument configs found under {path}", "target.empty"))
        else:
            targets.append(_check_path(path))
    return targets


def _violation_text(violation: Violation) -> str:
    code = f"[{violation.code}] " if violation.code else ""
    location = ".".join(str(part) for part in violation.loc)
    prefix = f"{location}: " if location else ""
    return f"{code}{prefix}{violation.msg}".replace("\n", "\n    ")


def _write_text(checks: list[TargetCheck], output: TextIO) -> None:
    if not checks:
        output.write("No installed instruments found.\n")
        return

    for index, checked in enumerate(checks):
        output.write(f"{checked.path}: {'valid' if checked.ok else 'invalid'}\n")
        output.writelines(f"  - {_violation_text(violation)}\n" for violation in checked.violations)
        if index != len(checks) - 1:
            output.write("\n")

    valid = sum(checked.ok for checked in checks)
    invalid = len(checks) - valid
    output.write(f"\nChecked {len(checks)} target(s): {valid} valid, {invalid} invalid\n")


def _write_json(checks: list[TargetCheck], output: TextIO) -> None:
    payload = {
        "ok": all(checked.ok for checked in checks),
        "targets": [
            {
                "path": str(checked.path),
                "ok": checked.ok,
                "violations": [
                    violation.model_dump(mode="json", exclude_none=True) for violation in checked.violations
                ],
            }
            for checked in checks
        ],
    }
    json.dump(payload, output, indent=2)
    output.write("\n")


def run_check(paths: list[Path], *, as_json: bool, output: TextIO) -> int:
    """Check targets, render the result, and return a process exit code."""
    load_voxel_env()
    checks = collect_checks(paths)
    if as_json:
        _write_json(checks, output)
    else:
        _write_text(checks, output)

    if any(
        violation.code is not None and violation.code.startswith("target.")
        for checked in checks
        for violation in checked.violations
    ):
        return 2
    return 0 if all(checked.ok for checked in checks) else 1
