from __future__ import annotations

import pytest

from kyamlgen.presets import curated_kinds, is_curated, preset_for
from kyamlgen.schemas import load_bundle
from kyamlgen.semantics import analyse
from kyamlgen.validate import SchemaValidator, check_form
from kyamlgen.widgets import WidgetBuilder

VERSION = "1.31.0"


@pytest.fixture(scope="module")
def bundle():
    return load_bundle(VERSION)


@pytest.fixture(scope="module")
def builder(bundle):
    return WidgetBuilder(bundle)


@pytest.fixture(scope="module")
def validator(bundle):
    return SchemaValidator(bundle)


def test_there_are_seventeen_curated_presets() -> None:
    assert len(curated_kinds()) == 17


def test_every_preset_is_a_manifest_with_a_kind() -> None:
    for kind in curated_kinds():
        manifest = preset_for(kind)
        assert manifest is not None
        assert manifest["kind"] == kind
        assert manifest["apiVersion"]
        assert manifest.get("metadata", {}).get("name")


def test_preset_for_returns_a_copy() -> None:
    """A caller mutating the preset must not corrupt the cached original."""
    first = preset_for("Deployment")
    first["metadata"]["name"] = "mutated"
    assert preset_for("Deployment")["metadata"]["name"] == "my-app"


def test_is_curated() -> None:
    assert is_curated("Deployment")
    assert not is_curated("Endpoints")


def test_no_preset_for_an_unknown_kind() -> None:
    assert preset_for("NotAKind") is None


@pytest.mark.parametrize("kind", curated_kinds())
def test_every_preset_validates_cleanly(
    kind: str, builder: WidgetBuilder, validator: SchemaValidator
) -> None:
    """A preset that produces a finding on load is a bad advertisement."""
    manifest = preset_for(kind)
    tree = builder.build(kind, manifest["apiVersion"])
    issues = check_form(tree, manifest) + validator.check(manifest) + analyse([manifest])
    assert not issues, "\n".join(f"{i.level}: {i.message}" for i in issues)


@pytest.mark.parametrize("kind", curated_kinds())
def test_curated_presets_use_only_common_fields(kind: str, builder: WidgetBuilder) -> None:
    """A preset must not set a field the form hides behind "advanced".

    This is the executable form of "filled only to that level which people usually
    use".  A preset that set an advanced field would put a value in the output that
    the user cannot see or change in the form.
    """
    manifest = preset_for(kind)
    tree = builder.build(kind, manifest["apiVersion"])
    hidden = _advanced_paths(tree)
    used = _set_paths(manifest, tree)
    assert not (used & hidden), f"advanced fields set by the preset: {sorted(used & hidden)}"


def test_deployment_and_service_presets_form_a_clean_bundle() -> None:
    """The two presets are designed to work together out of the box."""
    deployment = preset_for("Deployment")
    service = preset_for("Service")
    assert analyse([deployment, service]) == []
    assert deployment["metadata"]["labels"]["app"] == service["spec"]["selector"]["app"]
    # The Service targets the *named* container port, so the two stay in step.
    assert service["spec"]["ports"][0]["targetPort"] == "http"
    container_ports = deployment["spec"]["template"]["spec"]["containers"][0]["ports"]
    assert [port["name"] for port in container_ports] == ["http"]


def test_the_preset_selector_and_the_template_labels_agree() -> None:
    """The Deployment preset must not ship the mismatch it warns about."""
    deployment = preset_for("Deployment")
    selector = deployment["spec"]["selector"]["matchLabels"]
    labels = deployment["spec"]["template"]["metadata"]["labels"]
    assert selector == labels


# -- helpers ---------------------------------------------------------------


def _advanced_paths(tree: dict) -> set[tuple[str, ...]]:
    """Every path in the tree whose field is hidden behind "advanced"."""
    found: set[tuple[str, ...]] = set()

    def walk(node: dict, path: tuple[str, ...]) -> None:
        for child in node.get("children", []):
            child_path = path + (child["name"],)
            if child.get("advanced"):
                found.add(child_path)
            walk(child, child_path)
        item = node.get("item")
        if item:
            walk(item, path + ("*",))

    walk(tree, ())
    return found


def _set_paths(manifest: dict, tree: dict) -> set[tuple[str, ...]]:
    """Every path the manifest actually sets."""
    found: set[tuple[str, ...]] = set()

    def walk(value, node: dict, path: tuple[str, ...]) -> None:
        kind = node.get("kind")
        if kind == "object":
            children = {child["name"]: child for child in node.get("children", [])}
            for key, item in (value or {}).items():
                child = children.get(key)
                if child is None:
                    continue
                walk(item, child, path + (key,))
            return
        if kind == "array":
            item = node.get("item") or {}
            for index, entry in enumerate(value or []):
                walk(entry, item, path + (str(index),))
            return
        if kind == "map":
            for key in value or {}:
                found.add(path + (key,))
            return
        found.add(path)

    walk(manifest, tree, ())
    return found
