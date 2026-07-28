"""Deterministic discovery helpers for file-based scientific workflows."""

from __future__ import annotations

import os
from collections.abc import Iterable


def sorted_matching_files(
    directory: str,
    suffixes: Iterable[str],
    *,
    exclude: Iterable[str] = (),
) -> list[str]:
    """Return matching file names in a stable, case-insensitive order."""
    normalized_suffixes = tuple(suffix.lower() for suffix in suffixes)
    excluded = set(exclude)
    return sorted(
        (
            name
            for name in os.listdir(directory)
            if name not in excluded and name.lower().endswith(normalized_suffixes)
        ),
        key=lambda name: (name.casefold(), name),
    )
