from __future__ import annotations

import yaml

from kyamlgen.render import order_mapping, parse_yaml, prune, to_bundle_yaml, to_yaml


def test_keys_are_ordered_the_way_manifests_are_written() -> None:
    manifest = {
        "kind": "Deployment",
        "apiVersion": "apps/v1",
        "spec": {
            "template": {"spec": {"containers": [{"image": "nginx:1.27", "name": "web"}]}},
            "selector": {"matchLabels": {"app": "api"}},
            "replicas": 2,
        },
        "metadata": {"name": "api"},
    }
    text = to_yaml(manifest)
    lines = [line for line in text.splitlines() if line and not line.startswith(" ")]
    assert lines[0] == "apiVersion: apps/v1"
    assert lines[1] == "kind: Deployment"
    assert lines[2] == "metadata:"
    assert lines[3] == "spec:"
    assert text.index("replicas:") < text.index("selector:") < text.index("template:")
    assert text.index("name: web") < text.index("image: nginx:1.27")


def test_user_keyed_maps_keep_their_order() -> None:
    manifest = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "cfg"},
        "data": {"zebra": "1", "apple": "2", "mango": "3"},
    }
    text = to_yaml(manifest)
    assert text.index("zebra") < text.index("apple") < text.index("mango")


def test_yaml_one_booleans_are_quoted() -> None:
    """Kubernetes parses YAML as YAML 1.1, where a bare `on` is a boolean."""
    manifest = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "cfg"},
        "data": {"feature": "on", "other": "yes"},
    }
    text = to_yaml(manifest)
    assert "feature: 'on'" in text
    assert "other: 'yes'" in text
    parsed = yaml.safe_load(text)
    assert parsed["data"]["feature"] == "on"
    assert parsed["data"]["other"] == "yes"


def test_numeric_strings_are_quoted() -> None:
    manifest = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "cfg"},
        "data": {"PORT": "80"},
    }
    parsed = yaml.safe_load(to_yaml(manifest))
    assert parsed["data"]["PORT"] == "80"


def test_prune_drops_empty_values() -> None:
    value = {
        "metadata": {"name": "", "labels": {}},
        "spec": {"replicas": 0, "paused": False, "items": []},
    }
    cleaned = prune(value)
    assert cleaned == {"spec": {"replicas": 0, "paused": False}}


def test_bundle_yaml_uses_document_separators() -> None:
    manifests = [
        {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "a"}},
        {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "b"}},
    ]
    text = to_bundle_yaml(manifests)
    assert text.count("---") == 2
    documents = parse_yaml(text)
    assert [doc["metadata"]["name"] for doc in documents] == ["a", "b"]


def test_bundle_yaml_keeps_metadata_even_when_empty() -> None:
    text = to_bundle_yaml([{"apiVersion": "v1", "kind": "ConfigMap"}])
    assert "metadata: {}" in text


def test_order_mapping_leaves_scalars_alone() -> None:
    assert order_mapping("hello") == "hello"
    assert order_mapping(3) == 3
