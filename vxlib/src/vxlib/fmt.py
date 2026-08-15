"""Formatting helpers shared across Voxel packages."""

import re


def slugify(name: str) -> str:
    """Convert a display name to a filesystem-friendly slug."""
    slug = name.strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-")


def display_name(name: str, replacements: dict[str, str] | None = None) -> str:
    """Convert an identifier into a human-readable name."""
    chars = {"-": " ", "_": " "}
    if replacements:
        chars.update(replacements)

    for old, new in chars.items():
        name = name.replace(old, new)

    return name.title()


__all__ = ["display_name", "slugify"]
