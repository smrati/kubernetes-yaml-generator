"""Validation.

Three layers run over a submitted manifest:

1. **Form-time** — checks driven by the widget tree: required fields, numeric ranges,
   name formats, quantity syntax.
2. **JSON Schema** — the bundled Kubernetes schema in its ``additionalProperties:
   false`` variant, which rejects unknown fields, wrong types and invalid enum values.
3. **Semantic** — see :mod:`kyamlgen.semantics`; cross-object rules that no schema can
   express.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import jsonschema
from referencing import Registry, Resource

from .schemas import SchemaBundle, SchemaError

DNS_1123_SUBDOMAIN = re.compile(
    r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$"
)
DNS_1123_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
LABEL_VALUE = re.compile(r"^(([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9])?$")
QUANTITY = re.compile(r"^\d+(\.\d+)?([EPTGMK]i?|[mk])?$")
IMAGE_WITH_TAG = re.compile(r"^[^:@/]+(:[^:@/]+)?(@sha256:[0-9a-f]{64})$")

#: Kubernetes object names are DNS-1123 subdomains of at most 253 characters.
MAX_NAME_LENGTH = 253
MAX_NAMESPACE_LENGTH = 63
MAX_LABEL_LENGTH = 63


@dataclass
class Issue:
    """One validation finding."""

    level: str  # "error" | "warning"
    code: str
    message: str
    path: list[str] = field(default_factory=list)
    object_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "objectIndex": self.object_index,
        }


# -- form-time checks -------------------------------------------------------


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _walk(tree: dict[str, Any], value: Any) -> Iterator[tuple[dict[str, Any], Any, list[str]]]:
    """Walk the widget tree alongside a submitted value.

    Yields ``(widget, value, path)`` for every node that exists in the submission,
    plus the node itself for an object that is present but incomplete.

    The subtlety here is that a *missing* object must not make its own required
    children look missing.  ``lifecycle`` is optional, and nothing inside it is
    required, so an absent ``lifecycle`` must not produce "Port is required" from
    ``lifecycle.preStop.tcpSocket.port``.  A present-but-empty object, on the other
    hand, genuinely does have missing required children.
    """
    kind = tree.get("kind")
    yield tree, value, tree.get("path", [])

    if kind == "object":
        if not isinstance(value, dict):
            return
        for child in tree.get("children", []):
            yield from _walk(child, value.get(child["name"]))
        return

    if kind == "array":
        if not isinstance(value, list):
            return
        template = tree.get("item") or {}
        for item in value:
            yield from _walk(template, item)


def check_form(tree: dict[str, Any], value: Any) -> list[Issue]:
    """Validate a submitted object against the widget tree."""
    issues: list[Issue] = []

    # Required fields.
    for widget, child_value, _ in _walk(tree, value):
        if widget.get("required") and _is_blank(child_value):
            issues.append(
                Issue(
                    level="error",
                    code="required",
                    message=f"{widget['label']} is required.",
                    path=list(widget.get("path", [])),
                )
            )

    for widget, child_value, path in _walk(tree, value):
        if _is_blank(child_value):
            continue
        issues.extend(_check_value(widget, child_value, path))

    return issues


def _check_value(widget: dict[str, Any], value: Any, path: list[str]) -> list[Issue]:  # noqa: PLR0912
    issues: list[Issue] = []
    kind = widget.get("kind")
    name = widget.get("name", "")

    if kind == "integer":
        if not isinstance(value, int):
            issues.append(
                Issue("error", "type", f"{widget['label']} must be a whole number.", path)
            )
            return issues
        low = widget.get("min")
        high = widget.get("max")
        if low is not None and value < low:
            issues.append(
                Issue("error", "range", f"{widget['label']} must be at least {low}.", path)
            )
        if high is not None and value > high:
            issues.append(
                Issue("error", "range", f"{widget['label']} must be at most {high}.", path)
            )

    elif kind == "select":
        allowed = [str(option) for option in (widget.get("enum") or [])]
        if allowed and str(value) not in allowed:
            issues.append(
                Issue(
                    "error",
                    "enum",
                    f"{widget['label']} must be one of: {', '.join(allowed)}.",
                    path,
                )
            )

    elif kind == "quantity":
        text = str(value).strip()
        if not QUANTITY.match(text):
            issues.append(
                Issue(
                    "error",
                    "quantity",
                    f"{widget['label']} must be a Kubernetes quantity such as "
                    f"'500m', '128Mi' or '1'.",
                    path,
                )
            )

    elif kind == "int-or-string":
        text = str(value).strip()
        if text and not text.isdigit():
            issues.append(
                Issue(
                    "error",
                    "int-or-string",
                    f"{widget['label']} must be a port number or a port name.",
                    path,
                )
            )

    elif kind == "string" and name == "name" and path[:2] == ["metadata", "name"]:
        text = str(value)
        if len(text) > MAX_NAME_LENGTH or not DNS_1123_SUBDOMAIN.match(text):
            issues.append(
                Issue(
                    "error",
                    "name",
                    "Name must be a lowercase RFC 1123 subdomain: letters, digits, "
                    "'-' and '.', starting and ending with a letter or digit.",
                    path,
                )
            )

    elif kind == "string" and name == "namespace":
        text = str(value)
        if len(text) > MAX_NAMESPACE_LENGTH or not DNS_1123_LABEL.match(text):
            issues.append(
                Issue(
                    "error",
                    "namespace",
                    "Namespace must be a lowercase RFC 1123 label of at most 63 characters.",
                    path,
                )
            )

    elif kind == "map":
        style = widget.get("mapStyle", "generic")
        value_kind = widget.get("valueKind", "string")
        for key, map_value in (value or {}).items():
            if style in ("labels", "annotations") and (
                len(key) > MAX_LABEL_LENGTH or not _is_qualified_name(key)
            ):
                issues.append(
                    Issue(
                        "error",
                        "label-key",
                        f"'{key}' is not a valid label key.",
                        path,
                    )
                )
            if style == "labels" and isinstance(map_value, str):
                if len(map_value) > MAX_LABEL_LENGTH or not LABEL_VALUE.match(map_value):
                    issues.append(
                        Issue(
                            "error",
                            "label-value",
                            f"Value of '{key}' is not a valid label value.",
                            path,
                        )
                    )
            elif style == "generic" and value_kind == "quantity":
                if not QUANTITY.match(str(map_value).strip()):
                    issues.append(
                        Issue(
                            "error",
                            "quantity",
                            f"'{key}' must be a Kubernetes quantity such as '500m' or '128Mi'.",
                            path,
                        )
                    )
            elif (
                style == "generic"
                and value_kind == "int-or-string"
                and not str(map_value).strip().isdigit()
            ):
                issues.append(
                    Issue(
                        "error",
                        "int-or-string",
                        f"'{key}' must be a number or a name.",
                        path,
                    )
                )

    return issues


def _is_qualified_name(key: str) -> bool:
    """Validate a label key: optional DNS-subdomain prefix plus a 63-char name."""
    if "/" in key:
        prefix, _, name = key.partition("/")
        if not name or len(name) > MAX_LABEL_LENGTH:
            return False
        if not DNS_1123_SUBDOMAIN.match(prefix):
            return False
        return bool(re.match(r"^[A-Za-z0-9]([-A-Za-z0-9_.]*[A-Za-z0-9])?$", name))
    if not key or len(key) > MAX_LABEL_LENGTH:
        return False
    return bool(re.match(r"^[A-Za-z0-9]([-A-Za-z0-9_.]*[A-Za-z0-9])?$", key))


# -- JSON Schema layer ------------------------------------------------------


def _registry(bundle: SchemaBundle) -> Registry:
    """Registry that can resolve the bundle's cross-file ``$ref`` pointers."""
    resource = Resource.from_contents(bundle.kind_schema("Deployment", "apps/v1"))
    definitions = Resource.from_contents(bundle._definitions_doc)
    registry = resource @ Registry()
    return definitions @ registry


class SchemaValidator:
    """Validates a manifest against the bundled Kubernetes schema."""

    def __init__(self, bundle: SchemaBundle) -> None:
        self.bundle = bundle
        self._validators: dict[tuple[str, str], jsonschema.protocols.Validator] = {}

    def validator_for(self, kind: str, api_version: str) -> Any:
        key = (kind, api_version)
        if key not in self._validators:
            schema = self.bundle.kind_schema(kind, api_version)
            registry = self._registry_for(schema)
            self._validators[key] = jsonschema.validators.Draft202012Validator(
                schema, registry=registry
            )
        return self._validators[key]

    def _registry_for(self, schema: dict[str, Any]) -> Registry:
        resource = Resource.from_contents(schema)
        definitions = Resource.from_contents(self.bundle._definitions_doc)
        registry = resource @ Registry()
        return definitions @ registry

    def check(self, manifest: dict[str, Any]) -> list[Issue]:
        """Validate one manifest object."""
        kind = manifest.get("kind")
        api_version = manifest.get("apiVersion")
        if not kind or not api_version:
            return [
                Issue(
                    "error",
                    "identity",
                    "Every object needs an apiVersion and a kind.",
                )
            ]
        try:
            validator = self.validator_for(kind, api_version)
        except (SchemaError, KeyError) as exc:  # unknown kind or version
            return [Issue("error", "unknown-kind", f"Cannot validate {kind}: {exc}")]

        issues: list[Issue] = []
        for error in validator.iter_errors(manifest):
            issues.append(
                Issue(
                    level="error",
                    code="schema",
                    message=_describe(error),
                    path=_path_from(error),
                )
            )
        return issues


def _path_from(error: jsonschema.ValidationError) -> list[str]:
    """Convert a jsonschema error path into a widget path."""
    parts: list[str] = []
    for part in error.absolute_path:
        parts.append(str(part))
    return parts


def _describe(error: jsonschema.ValidationError) -> str:
    """A readable one-line description of a schema violation."""
    if error.validator == "additionalProperties":
        quoted = error.message.split("'")
        extra = sorted(set(quoted[1::2]))
        return f"Unknown field: {', '.join(extra)}." if extra else error.message
    if error.validator == "required":
        return f"Missing required field: {error.message}."
    if error.validator == "enum":
        allowed = ", ".join(str(value) for value in error.validator_value)
        return f"{error.message}. Allowed values: {allowed}."
    return error.message
