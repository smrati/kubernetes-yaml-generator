from __future__ import annotations

import pytest

from kyamlgen.schemas import (
    DEFS_QUANTITY,
    SchemaError,
    available_versions,
    default_version,
    find_kind,
    kind_index,
    kind_schema_filename,
    load_bundle,
)


def test_bundle_covers_a_range_of_versions() -> None:
    versions = available_versions()
    assert "1.31.0" in versions
    assert len(versions) >= 10
    assert default_version() == versions[-1]


@pytest.mark.parametrize(
    ("kind", "api_version", "expected"),
    [
        ("Deployment", "apps/v1", "deployment-apps-v1.json"),
        ("ConfigMap", "v1", "configmap-v1.json"),
        ("Ingress", "networking.k8s.io/v1", "ingress-networking-v1.json"),
        ("ClusterRole", "rbac.authorization.k8s.io/v1", "clusterrole-rbac-v1.json"),
        (
            "HorizontalPodAutoscaler",
            "autoscaling/v2",
            "horizontalpodautoscaler-autoscaling-v2.json",
        ),
    ],
)
def test_kind_schema_filename_matches_the_bundle_convention(
    kind: str, api_version: str, expected: str
) -> None:
    assert kind_schema_filename(kind, api_version) == expected


def test_kind_index_finds_every_top_level_kind() -> None:
    index = kind_index("1.31.0")
    assert ("apps", "v1", "Deployment") in index
    assert ("", "v1", "ConfigMap") in index
    assert ("networking.k8s.io", "v1", "Ingress") in index
    assert all(ref.filename.endswith(".json") for ref in index.values())


def test_find_kind_prefers_the_newest_version() -> None:
    ref = find_kind("1.31.0", "HorizontalPodAutoscaler")
    assert ref is not None
    assert ref.version == "v2"


def test_resolve_follows_a_ref_and_keeps_siblings() -> None:
    bundle = load_bundle("1.31.0")
    node = {
        "$ref": "#/$defs/io.k8s.api.core.v1.ContainerPort",
        "description": "A port to expose from the container.",
    }
    resolved = bundle.resolve(node)
    assert resolved["description"] == "A port to expose from the container."
    assert "containerPort" in resolved["properties"]


def test_resolve_handles_the_absolute_definitions_url() -> None:
    bundle = load_bundle("1.31.0")
    node = {
        "$ref": "https://kubernetes.io/api/_definitions.json#/$defs/io.k8s.api.core.v1.ContainerPort"
    }
    assert "containerPort" in bundle.resolve(node)["properties"]


def test_quantity_is_recognised_as_a_definition() -> None:
    bundle = load_bundle("1.31.0")
    assert bundle.definition_name({"$ref": f"#/$defs/{DEFS_QUANTITY}"}) == DEFS_QUANTITY


def test_unknown_kind_raises() -> None:
    bundle = load_bundle("1.31.0")
    with pytest.raises(SchemaError):
        bundle.kind_schema("NotAKind", "apps/v1")
