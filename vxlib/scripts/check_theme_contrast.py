# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Report WCAG 2.1 contrast ratios for the web UI theme tokens.

Checks the pairings that carry meaning: text on surfaces, borders on
surfaces, and semantic foreground/background pairs. Rows below their WCAG
threshold are flagged. Note that decorative panel dividers are exempt from
the 3:1 non-text rule, so a flagged `border` row is informational.

Usage:
    uv run vxlib/scripts/check_theme_contrast.py
    uv run vxlib/scripts/check_theme_contrast.py web/ui/src/lib/themes/jetbrains.dark.css
    uv run vxlib/scripts/check_theme_contrast.py --only-fails
"""

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
THEMES_DIR = REPO_ROOT / "web" / "ui" / "src" / "lib" / "themes"

SURFACES = ["canvas", "surface", "elevated", "element-bg"]
TEXT_TOKENS = ["fg", "fg-muted", "fg-faint", "fg-accent"]
BORDER_TOKENS = ["border", "border-variant", "border-focused", "border-selected"]
SEMANTICS = ["danger", "success", "warning", "info"]


def parse_tokens(css: str) -> dict[str, str]:
    """Map `--token` to a #rrggbb value, resolving one level of var() aliasing."""
    tokens: dict[str, str] = {}
    for name, val in re.findall(r"--([\w-]+):\s*([^;]+);", css):
        if m := re.match(r"#([0-9a-fA-F]{6})$", val.strip()):
            tokens[name] = "#" + m.group(1).lower()
    for name, target in re.findall(r"--([\w-]+):\s*var\(--([\w-]+)\)", css):
        if target in tokens:
            tokens[name] = tokens[target]
    return tokens


def _to_linear(channel: float) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _to_linear(r) + 0.7152 * _to_linear(g) + 0.0722 * _to_linear(b)


def contrast_ratio(fg: str, bg: str) -> float:
    hi, lo = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def grade_text(ratio: float) -> str:
    if ratio >= 7:
        return "AAA"
    if ratio >= 4.5:
        return "AA"
    if ratio >= 3:
        return "AA-large"
    return "FAIL"


def grade_ui(ratio: float) -> str:
    return "AA(3:1)" if ratio >= 3 else "FAIL"


def check(tokens: dict[str, str], fg: str, bg: str, kind: str, only_fails: bool) -> None:
    if fg not in tokens or bg not in tokens:
        return
    ratio = contrast_ratio(tokens[fg], tokens[bg])
    grade = grade_text(ratio) if kind == "text" else grade_ui(ratio)
    failing = grade in ("FAIL", "AA-large")
    if only_fails and not failing:
        return
    flag = "  <--" if failing else ""
    print(f"  {fg:16s} on {bg:12s} {tokens[fg]} / {tokens[bg]}  {ratio:5.2f}:1  {grade}{flag}")


def report(path: Path, only_fails: bool) -> None:
    tokens = parse_tokens(path.read_text())
    print(f"\n### {path.name}")

    print("\n  TEXT on surfaces (AA=4.5, AAA=7, large=3)")
    for token in TEXT_TOKENS:
        for surface in SURFACES:
            check(tokens, token, surface, "text", only_fails)

    print("\n  BORDERS on surfaces (non-text 3:1; dividers exempt)")
    for token in BORDER_TOKENS:
        for surface in SURFACES:
            check(tokens, token, surface, "ui", only_fails)

    print("\n  SEMANTIC fg on its own bg (text)")
    for name in SEMANTICS:
        check(tokens, f"{name}-fg", f"{name}-bg", "text", only_fails)

    print("\n  ACCENTS on surface (text/icon)")
    for name in [*SEMANTICS, "primary", "fg-accent"]:
        check(tokens, name, "surface", "text", only_fails)

    print("\n  INTERACTIVE fg on fill (text)")
    check(tokens, "primary-fg", "primary", "text", only_fails)
    check(tokens, "secondary-fg", "secondary", "text", only_fails)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "themes",
        nargs="*",
        type=Path,
        help="theme CSS files (default: every *.css in the themes dir except base/index)",
    )
    parser.add_argument("--only-fails", action="store_true", help="show only rows below threshold")
    args = parser.parse_args()

    paths = args.themes or sorted(p for p in THEMES_DIR.glob("*.css") if p.stem not in ("base", "index"))
    for path in paths:
        report(path, args.only_fails)


if __name__ == "__main__":
    main()
