"""Curated starting-point manifests.

A preset is a *real manifest*, not a form definition.  It is loaded, validated
and rendered by exactly the same code paths as anything the user produces, so a
broken preset shows up as a failing test rather than as a confusing form.

Only kinds people actually author have a preset.  The rest open empty, which is
honest: a generated skeleton for an obscure kind teaches less than a blank form
with the required fields called out.
"""

from __future__ import annotations

import copy
import functools
from pathlib import Path
from typing import Any

import yaml

#: Directory holding the hand-written presets, one YAML file per kind.
CURATED_DIR = Path(__file__).parent / "curated"


@functools.lru_cache(maxsize=1)
def _presets() -> dict[str, dict[str, Any]]:
    """Every curated preset, keyed by kind."""
    presets: dict[str, dict[str, Any]] = {}
    for path in sorted(CURATED_DIR.glob("*.yaml")):
        manifest = yaml.safe_load(path.read_text())
        if not isinstance(manifest, dict):
            continue
        kind = manifest.get("kind")
        if not kind:
            raise ValueError(f"{path.name} has no 'kind'")
        presets[kind] = manifest
    return presets


@functools.lru_cache(maxsize=1)
def curated_kinds() -> tuple[str, ...]:
    """The kinds that have a curated preset, sorted."""
    return tuple(sorted(_presets()))


def preset_for(kind: str) -> dict[str, Any] | None:
    """The curated preset for a kind, or ``None`` if there is not one.

    A copy is returned so a caller cannot mutate the cached original.
    """
    manifest = _presets().get(kind)
    return copy.deepcopy(manifest) if manifest is not None else None


def is_curated(kind: str) -> bool:
    """Whether a kind has a hand-written preset."""
    return kind in _presets()
