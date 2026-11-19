from __future__ import annotations

from kyamlgen.schemas import kind_index, load_bundle
from kyamlgen.widgets import SERVER_MANAGED_METADATA, WidgetBuilder


def build(kind: str, api_version: str, version: str = "1.31.0") -> dict:
    return WidgetBuilder(load_bundle(version)).build(kind, api_version)


def find(node: dict, path: list[str]) -> dict | None:
    """Find a widget by its path, using '*' for array items."""
    if not path:
        return node
    name = path[0]
    children = node.get("children") or []
    for child in children:
        if child.get("name") == name:
            return find(child, path[1:])
    if node.get("kind") == "array" and node.get("item"):
        return find(node["item"], path)
    return None


def test_deployment_tree_has_the_expected_shape() -> None:
    tree = build("Deployment", "apps/v1")
    assert tree["kind"] == "object"
    names = [child["name"] for child in tree["children"]]
    assert names == ["metadata", "spec"]


def test_status_is_never_offered() -> None:
    tree = build("Deployment", "apps/v1")
    assert all(child["name"] != "status" for child in tree["children"])


def test_server_managed_metadata_is_hidden() -> None:
    tree = build("Deployment", "apps/v1")
    metadata = find(tree, ["metadata"])
    assert metadata is not None
    shown = {child["name"] for child in metadata["children"]}
    assert not shown & SERVER_MANAGED_METADATA
    assert {"name", "namespace", "labels", "annotations"} <= shown


def test_metadata_name_is_required_even_though_the_schema_does_not_say_so() -> None:
    tree = build("Deployment", "apps/v1")
    name = find(tree, ["metadata", "name"])
    assert name is not None
    assert name["required"] is True


def test_labels_render_as_a_map() -> None:
    tree = build("Deployment", "apps/v1")
    labels = find(tree, ["metadata", "labels"])
    assert labels is not None
    assert labels["kind"] == "map"


def test_target_port_uses_the_int_or_string_widget() -> None:
    tree = build("Service", "v1")
    target = find(tree, ["spec", "ports", "targetPort"])
    assert target is not None
    assert target["kind"] == "int-or-string"


def test_resource_limits_use_the_quantity_widget() -> None:
    tree = build("Deployment", "apps/v1")
    limits = find(tree, ["spec", "template", "spec", "containers", "resources", "limits"])
    assert limits is not None
    assert limits["kind"] == "map"
    assert limits["valueKind"] == "quantity"


def test_container_image_is_required_in_practice() -> None:
    tree = build("Deployment", "apps/v1")
    image = find(tree, ["spec", "template", "spec", "containers", "image"])
    assert image is not None
    assert image["required"] is True


def test_rare_pod_spec_fields_are_advanced() -> None:
    tree = build("Deployment", "apps/v1")
    affinity = find(tree, ["spec", "template", "spec", "affinity"])
    assert affinity is not None
    assert affinity["advanced"] is True
    containers = find(tree, ["spec", "template", "spec", "containers"])
    assert containers is not None
    assert containers["advanced"] is False


def test_service_type_is_a_select() -> None:
    tree = build("Service", "v1")
    service_type = find(tree, ["spec", "type"])
    assert service_type is not None
    assert service_type["kind"] == "select"
    assert "ClusterIP" in service_type["enum"]


def test_cronjob_reaches_its_job_template() -> None:
    tree = build("CronJob", "batch/v1")
    schedule = find(tree, ["spec", "schedule"])
    assert schedule is not None
    assert schedule["kind"] == "string"
    containers = find(tree, ["spec", "jobTemplate", "spec", "template", "spec", "containers"])
    assert containers is not None
    assert containers["kind"] == "array"


def test_every_kind_in_the_bundle_builds_a_tree() -> None:
    """The generic engine must not fall over on any kind."""
    bundle = load_bundle("1.31.0")
    builder = WidgetBuilder(bundle)
    failures = []
    for ref in kind_index("1.31.0").values():
        try:
            tree = builder.build(ref.kind, ref.api_version)
        except Exception as exc:  # noqa: BLE001 - the point is to collect every failure
            failures.append(f"{ref.api_version}/{ref.kind}: {exc}")
            continue
        if tree["kind"] != "object":
            failures.append(f"{ref.api_version}/{ref.kind}: root is {tree['kind']}")
    assert not failures, "kinds that failed to build:\n" + "\n".join(failures[:20])
