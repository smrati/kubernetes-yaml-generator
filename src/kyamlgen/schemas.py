"""Access to the Kubernetes JSON schemas bundled with ``kubernetes-validate``.

The bundle is an offline copy of the upstream Kubernetes OpenAPI schemas
(https://github.com/yannh/kubernetes-json-schema), covering Kubernetes v1.25.0 through
v1.37.0 in both a permissive (``local``) and an ``additionalProperties: false`` variant
(``local-strict``).

We read the schema files directly rather than going through
``kubernetes_validate.validate()`` for two reasons:

1. The form is *generated from* the schema, so we need the schema itself, not a verdict.
2. ``validate()`` does not require a top-level ``spec`` to be present, which means a
   ``Deployment`` with no ``spec`` passes.  Our semantic layer covers that gap.
"""

from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

SCHEMA_PACKAGE = "kubernetes_validate"
SCHEMA_DIR = "kubernetes-json-schema"

#: Directory names look like ``v1.31.0-local`` and ``v1.31.0-local-strict``.
_VERSION_DIR_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)-local(?P<strict>-strict)?$")

#: ``#/$defs/io.k8s.api.core.v1.Container`` -> the definition name.
_DEF_REF_RE = re.compile(r"#/\$defs/(?P<name>[^#]+)$")

#: Definition names that need a bespoke widget rather than the generic mapping.
DEFS_INT_OR_STRING = "io.k8s.apimachinery.pkg.util.intstr.IntOrString"
DEFS_QUANTITY = "io.k8s.apimachinery.pkg.api.resource.Quantity"
DEFS_OBJECT_META = "io.k8s.apimachinery.pkg.apis.meta.v1.ObjectMeta"


class SchemaError(RuntimeError):
    """Raised when the schema bundle cannot satisfy a request."""


class UnsupportedRefError(SchemaError):
    """Raised for a ``$ref`` the bundle resolver does not understand."""


def version_key(version: str) -> tuple[int, ...]:
    """Sort key for a version string such as ``1.31.0`` or ``v1beta1``."""
    stripped = version.removeprefix("v")
    parts: list[int] = []
    for part in stripped.split("."):
        digits = "".join(char for char in part if char.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def bundle_root() -> Path:
    """Absolute path to the bundled ``kubernetes-json-schema`` directory."""
    return Path(str(resources.files(SCHEMA_PACKAGE).joinpath(SCHEMA_DIR)))


def available_versions() -> list[str]:
    """Kubernetes versions present in the bundle, oldest first."""
    root = bundle_root()
    if not root.is_dir():
        raise SchemaError(f"schema bundle not found at {root}")
    versions = {
        match.group("version")
        for match in (_VERSION_DIR_RE.match(entry.name) for entry in root.iterdir())
        if match
    }
    return sorted(versions, key=version_key)


def default_version() -> str:
    """Newest Kubernetes version in the bundle."""
    return available_versions()[-1]


def schema_dir(version: str, strict: bool = True) -> Path:
    """Directory holding the schema files for one Kubernetes version."""
    name = f"v{version}-local-strict" if strict else f"v{version}-local"
    path = bundle_root() / name
    if not path.is_dir():
        raise SchemaError(f"no schema directory for Kubernetes {version} (looked for {name})")
    return path


def kind_schema_filename(kind: str, api_version: str) -> str:
    """File name for a top-level kind schema.

    The bundle names files ``{kind}-{first-label-of-group}-v{version}.json``, so
    ``networking.k8s.io/v1`` collapses to ``networking-v1`` and the core group
    (``v1``) collapses to just ``v1``.
    """
    if "/" in api_version:
        group, version = api_version.split("/", 1)
        label = group.split(".")[0]
    else:
        label, version = "", api_version
    if label:
        return f"{kind.lower()}-{label}-{version}.json"
    return f"{kind.lower()}-{version}.json"


@dataclass(frozen=True)
class KindRef:
    """A top-level Kubernetes kind discovered in the schema bundle."""

    group: str
    version: str
    kind: str
    filename: str

    @property
    def api_version(self) -> str:
        return f"{self.group}/{self.version}" if self.group else self.version

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.group, self.version, self.kind)


@functools.cache
def kind_index(version: str) -> dict[tuple[str, str, str], KindRef]:
    """Map ``(group, version, kind)`` to the schema file that defines it.

    Built by reading the ``x-kubernetes-group-version-kind`` marker out of each schema
    file.  Scanning 635 files costs roughly 60ms, so it is done once and memoised.
    """
    index: dict[tuple[str, str, str], KindRef] = {}
    for path in sorted(schema_dir(version).glob("*.json")):
        if path.stem.startswith("_") or path.stem == "all":
            continue
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for gvk in data.get("x-kubernetes-group-version-kind") or []:
            group = gvk.get("group", "")
            ref = KindRef(group, gvk["version"], gvk["kind"], path.name)
            index[ref.key] = ref
    return index


def find_kind(version: str, kind: str, group: str | None = None) -> KindRef | None:
    """Look up a kind by name, optionally restricted to one API group."""
    index = kind_index(version)
    matches = [ref for ref in index.values() if ref.kind == kind]
    if group is not None:
        matches = [ref for ref in matches if ref.group == group]
    if not matches:
        return None
    # Prefer the newest version of the kind when the caller did not pin one.
    matches.sort(key=lambda ref: version_key(ref.version))
    return matches[-1]


class SchemaBundle:
    """Schemas for a single Kubernetes version, with ``$ref`` resolution."""

    def __init__(self, version: str, strict: bool = True) -> None:
        self.version = version
        self.strict = strict
        self.dir = schema_dir(version, strict)
        self._definitions_doc = json.loads((self.dir / "_definitions.json").read_text())
        self._kind_cache: dict[str, dict[str, Any]] = {}

    @property
    def definitions(self) -> dict[str, Any]:
        """The shared ``$defs`` table."""
        return self._definitions_doc["$defs"]

    def kind_schema(self, kind: str, api_version: str) -> dict[str, Any]:
        """Load the top-level schema for a kind.

        The file name is derived from the API group, but the bundle is not perfectly
        regular — the ``meta.k8s.io`` kinds are stored as ``apigroup-meta-v1.json``,
        for example.  So the derived name is only a fast path; the authoritative answer
        comes from the kind index, which is built from each file's own
        ``x-kubernetes-group-version-kind`` marker.
        """
        filename = kind_schema_filename(kind, api_version)
        if filename not in self._kind_cache:
            group, _, version = api_version.partition("/")
            if not version:
                group, version = "", api_version
            ref = kind_index(self.version).get((group, version, kind))
            if ref is not None:
                filename = ref.filename
            path = self.dir / filename
            if not path.is_file():
                raise SchemaError(f"no schema for {kind} in {api_version} (looked for {filename})")
            self._kind_cache[filename] = json.loads(path.read_text())
        return self._kind_cache[filename]

    def resolve(self, node: Any) -> Any:
        """Follow a ``$ref`` to its definition.

        Handles the three reference spellings that appear in the bundle:
        ``#/$defs/<name>``, ``/api/_definitions.json#/$defs/<name>`` and the absolute
        ``https://kubernetes.io/api/_definitions.json#/$defs/<name>`` form.  Sibling
        keys next to the ``$ref`` (typically ``description``) are preserved.
        """
        if not isinstance(node, dict) or "$ref" not in node:
            return node
        ref = node["$ref"]
        match = _DEF_REF_RE.search(ref)
        if not match:
            raise UnsupportedRefError(f"unsupported $ref: {ref}")
        name = match.group("name")
        target = self.definitions.get(name)
        if target is None:
            raise UnsupportedRefError(f"unknown definition in $ref: {ref}")
        siblings = {key: value for key, value in node.items() if key != "$ref"}
        if not siblings:
            return target
        merged = dict(target)
        merged.update(siblings)
        return merged

    def definition_name(self, node: Any) -> str | None:
        """Return the definition name a node points at, if it is a plain ``$ref``."""
        if isinstance(node, dict) and isinstance(node.get("$ref"), str):
            match = _DEF_REF_RE.search(node["$ref"])
            if match:
                return match.group("name")
        return None


@functools.cache
def load_bundle(version: str, strict: bool = True) -> SchemaBundle:
    """Memoised accessor for a :class:`SchemaBundle`."""
    return SchemaBundle(version, strict)
