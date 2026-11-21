"""The terminal and JSON report of a check: each target checked, with what is wrong in it."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO


class Finding(Protocol):
    """1 thing wrong in a target: a code, a message, and its place in the files."""

    @property
    def code(self) -> str | None: ...

    @property
    def msg(self) -> str: ...

    @property
    def loc(self) -> Sequence[str | int]: ...


@dataclass(frozen=True)
class CheckedTarget:
    """1 file or folder that was checked, and what is wrong in it."""

    path: Path
    ok: bool
    findings: Sequence[Finding] = ()


def _finding_text(finding: Finding) -> str:
    code = f"[{finding.code}] " if finding.code else ""
    location = ".".join(str(part) for part in finding.loc)
    prefix = f"{location}: " if location else ""
    return f"{code}{prefix}{finding.msg}".replace("\n", "\n    ")


def write_report(targets: Sequence[CheckedTarget], *, as_json: bool, output: TextIO, nothing: str) -> None:
    """Write each target and its findings, as text or as JSON. ``nothing`` is what the text says when there are no
    targets."""
    if as_json:
        payload = {
            "ok": all(target.ok for target in targets),
            "targets": [
                {
                    "path": str(target.path),
                    "ok": target.ok,
                    "violations": [{"code": f.code, "msg": f.msg, "loc": list(f.loc)} for f in target.findings],
                }
                for target in targets
            ],
        }
        json.dump(payload, output, indent=2)
        output.write("\n")
        return
    if not targets:
        output.write(f"{nothing}\n")
        return
    for index, target in enumerate(targets):
        output.write(f"{target.path}: {'valid' if target.ok else 'invalid'}\n")
        output.writelines(f"  - {_finding_text(finding)}\n" for finding in target.findings)
        if index != len(targets) - 1:
            output.write("\n")
    valid = sum(target.ok for target in targets)
    output.write(f"\nChecked {len(targets)} target(s): {valid} valid, {len(targets) - valid} invalid\n")


__all__ = ["CheckedTarget", "Finding", "write_report"]
